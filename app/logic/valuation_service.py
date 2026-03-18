"""
Epoch Ledger Portfolio Valuation Service

Implements:
- Pro-rata profit allocation by weighted active capital in a period
- Compounding across epochs (end_balance becomes next epoch start_balance)
- Cryptographic hash chaining per (internal_client_code, fund_name)
- Reconciliation against head_office_total with strict rollback on mismatch

Assumptions (documented to keep behavior deterministic):
- performance_rate is a decimal fraction for the full period (e.g. 0.05 for 5%)
- An investor is considered "active" starting at investment.date_transferred if present,
  else investment.date_deposited.
- Weighted capital uses amount_deposited × days_active within [start_date, end_date).
- Total profit for the fund over the period is:
    average_active_capital × performance_rate
  where average_active_capital = total_weighted_capital / period_days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from contextlib import nullcontext

from app.database.database import db
from app.Investments.model import Investment, Withdrawal, EpochLedger
from app.Batch.core_fund import CoreFund
from app.logic.institutional_validation_service import InstitutionalValidationService
from app.Batch.model import Batch


GENESIS_HASH = "0" * 64


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ledger_hash_payload(
    *,
    internal_client_code: str,
    fund_name: str,
    epoch_start: datetime,
    epoch_end: datetime,
    performance_rate: Decimal,
    start_balance: Decimal,
    deposits: Decimal,
    withdrawals: Decimal,
    profit: Decimal,
    end_balance: Decimal,
    previous_hash: str,
) -> str:
    # Stable, explicit field ordering (no locale, no float)
    return "|".join(
        [
            internal_client_code,
            fund_name.lower(),
            epoch_start.isoformat(),
            epoch_end.isoformat(),
            f"{performance_rate:.8f}",
            f"{start_balance:.2f}",
            f"{deposits:.2f}",
            f"{withdrawals:.2f}",
            f"{profit:.2f}",
            f"{end_balance:.2f}",
            previous_hash,
        ]
    )


@dataclass(frozen=True)
class InvestorPeriodInputs:
    internal_client_code: str
    principal_before_start: Decimal
    deposits_during_period: Decimal
    withdrawals_during_period: Decimal
    weighted_capital: Decimal


class PortfolioValuationService:
    @staticmethod
    def _period_days(start_date: datetime, end_date: datetime) -> int:
        """Calculate days in period. Includes both start and end dates."""
        days = (end_date - start_date).days + 1  # +1 to include both start and end date
        if days <= 0:
            raise ValueError("end_date must be after start_date (at least 1 day)")
        return days

    @staticmethod
    def _is_full_calendar_month(start_date: datetime, end_date: datetime) -> bool:
        """
        Determine if period covers a full calendar month (>= 28 days covering month boundary).
        
        Returns True if:
        - Period is >= 28 days
        - Period starts on or before the 1st of a month
        - Period ends on or after last day of that month
        """
        if (end_date - start_date).days < 27:  # <27 because we want >= 28 days
            return False
        
        # Check if period covers full month cycle
        return (start_date.day <= 1 and end_date.day >= 28) or \
               (start_date.day == 1 and (end_date - start_date).days >= 27)

    @staticmethod
    def _active_start(investment: Investment) -> datetime:
        return investment.date_transferred or investment.date_deposited

    @classmethod
    def _build_investor_inputs(
        cls,
        *,
        fund_id: int,
        fund_name: str | None,
        start_date: datetime,
        end_date: datetime,
        session,
    ) -> dict[str, InvestorPeriodInputs]:
        """Step A: Fetch investments for the fund where active_start < end_date.

        This method supports both:
        - Investments linked directly by `fund_id` (new data)
        - Investments linked by `fund_name` (legacy data before fund_id was set)

        The query avoids duplicates by filtering on (fund_id == fund_id) OR
        (fund_id is NULL AND lower(fund_name) == lower(fund_name)).
        """

        # Ensure we have a normalized fund name for legacy fallbacks
        fund_name = (fund_name or '').strip()

        investments_query = session.query(Investment).filter(
            or_(
                Investment.fund_id == fund_id,
                (Investment.fund_id == None) & (func.lower(Investment.fund_name) == fund_name.lower()),
            )
        )

        investments = investments_query.all()

        period_days = cls._period_days(start_date, end_date)

        # Aggregate per investor
        per_code = {}
        for inv in investments:
            active_start = cls._active_start(inv)
            if active_start is None:
                continue
            if active_start >= end_date:
                continue

            code = inv.internal_client_code
            amount = _to_decimal(inv.amount_deposited)

            # Deposits are treated as:
            # - principal_before_start if active_start < start_date
            # - deposits_during_period if start_date <= active_start < end_date
            if code not in per_code:
                per_code[code] = {
                    "principal_before_start": Decimal("0"),
                    "deposits_during_period": Decimal("0"),
                    "weighted_capital": Decimal("0"),
                }

            if active_start < start_date:
                per_code[code]["principal_before_start"] += amount
                days_active = (end_date - start_date).days
            else:
                per_code[code]["deposits_during_period"] += amount
                # If investor activated on the same calendar day as period start,
                # treat them as active for the full period (no partial day penalty)
                if active_start.date() == start_date.date():
                    days_active = (end_date - start_date).days
                else:
                    days_active = (end_date - active_start).days

            days_active = max(0, min(period_days, days_active))
            per_code[code]["weighted_capital"] += amount * Decimal(days_active)

        # Approved withdrawals in the period reduce both:
        withdrawals_rows = (
            session.query(Withdrawal)
            .filter(Withdrawal.fund_id == fund_id)
            .filter(Withdrawal.status == "Approved")
            .filter(Withdrawal.date_withdrawn >= start_date, Withdrawal.date_withdrawn < end_date)
            .all()
        )
        withdrawals_by_code = {}
        withdrawal_weight_by_code = {}
        for w in withdrawals_rows:
            amt = _to_decimal(w.amount)
            withdrawals_by_code[w.internal_client_code] = withdrawals_by_code.get(w.internal_client_code, Decimal("0")) + amt
            days_remaining = (end_date - max(start_date, w.date_withdrawn)).days
            days_remaining = max(0, days_remaining)
            withdrawal_weight_by_code[w.internal_client_code] = withdrawal_weight_by_code.get(w.internal_client_code, Decimal("0")) + (amt * Decimal(days_remaining))

        result = {}
        for code, agg in per_code.items():
            # Reduce weighted capital by approved withdrawals weighting
            agg["weighted_capital"] = agg["weighted_capital"] - withdrawal_weight_by_code.get(code, Decimal("0"))
            result[code] = InvestorPeriodInputs(
                internal_client_code=code,
                principal_before_start=_q2(agg["principal_before_start"]),
                deposits_during_period=_q2(agg["deposits_during_period"]),
                withdrawals_during_period=_q2(withdrawals_by_code.get(code, Decimal("0"))),
                weighted_capital=agg["weighted_capital"],  # keep high precision until allocation
            )
        return result

    @staticmethod
    def _get_previous_epoch_hash_and_end_balance(*, session, internal_client_code: str, fund_name: str, start_date: datetime):
        prev = (
            session.query(EpochLedger)
            .filter(EpochLedger.internal_client_code == internal_client_code)
            .filter(func.lower(EpochLedger.fund_name) == fund_name.lower())
            .filter(EpochLedger.epoch_end <= start_date)
            .order_by(EpochLedger.epoch_end.desc(), EpochLedger.id.desc())
            .first()
        )
        if not prev:
            return GENESIS_HASH, Decimal("0.00")
        return prev.current_hash, _to_decimal(prev.end_balance)

    @classmethod
    def create_epoch_ledger_for_fund(
        cls,
        *,
        fund_id: int,
        start_date: datetime,
        end_date: datetime,
        performance_rate: Decimal | float | str,
        head_office_total: Decimal | float | str,
        session=None,
    ):
        """
        Creates one EpochLedger row per investor for the given fund and period.
        Reconciles sum(end_balance) against head_office_total.

        Returns:
            dict summary (counts, totals)

        Raises:
            ValueError on reconciliation failure or invalid input.
        """
        if session is None:
            session = db.session

        perf_rate = _to_decimal(performance_rate)
        head_total = _q2(_to_decimal(head_office_total))

        fund = session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            raise ValueError(f"Fund with id {fund_id} not found")

        fund_name = fund.fund_name

        investor_inputs = cls._build_investor_inputs(
            fund_id=fund_id,
            fund_name=fund_name,
            start_date=start_date,
            end_date=end_date,
            session=session,
        )

        if not investor_inputs:
            raise ValueError("No eligible investments found for this fund in the given period")

        period_days = cls._period_days(start_date, end_date)
        total_weighted = sum((inp.weighted_capital for inp in investor_inputs.values()), Decimal("0"))
        if total_weighted <= 0:
            raise ValueError("Total weighted capital is zero; cannot allocate profit")

        # FLAT MONTH OVERRIDE: If period covers full calendar month (>= 28 days), 
        # apply performance rate as flat multiplier on total capital
        is_full_month = cls._is_full_calendar_month(start_date, end_date)
        
        if is_full_month:
            # Flat rate: total_capital * performance_rate (no day-weighted averaging)
            total_capital = sum(
                (inp.principal_before_start + inp.deposits_during_period 
                 for inp in investor_inputs.values()),
                Decimal("0")
            )
            total_profit = _q2(total_capital * perf_rate)
            print(f"[FLAT MONTH] Period {start_date.date()}-{end_date.date()} covers full month. Using flat multiplier: ${total_capital} × {perf_rate} = ${total_profit}")
        else:
            # Pro-rata: average_active_capital * performance_rate (day-weighted)
            avg_active_capital = (total_weighted / Decimal(period_days))
            total_profit = _q2(avg_active_capital * perf_rate)
            print(f"[PRO-RATA] Period {start_date.date()}-{end_date.date()} ({period_days} days). Using pro-rata: ${avg_active_capital:.2f} × {perf_rate} = ${total_profit}")

        created_rows = []

        # Transaction boundary: Let SQLAlchemy handle nested transactions naturally
        # If already in a transaction, begin_nested() creates a savepoint
        # If not in a transaction, begin() starts a new one
        try:
            # Always try to use begin_nested first (works both inside and outside transactions)
            # SQLAlchemy will automatically use a savepoint if we're in a transaction,
            # or start a new sublevel transaction if we're not
            with session.begin_nested():
                for code, inp in investor_inputs.items():
                    previous_hash, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                        session=session,
                        internal_client_code=code,
                        fund_name=fund_name,
                        start_date=start_date,
                    )

                    # Step C: compounding
                    start_balance = _q2(prev_end_balance + inp.principal_before_start)

                    # Step B: pro-rata profit
                    profit_share = (inp.weighted_capital / total_weighted)
                    profit = _q2(total_profit * profit_share)

                    end_balance = _q2(
                        start_balance + inp.deposits_during_period - inp.withdrawals_during_period + profit
                    )

                    payload = _ledger_hash_payload(
                        internal_client_code=code,
                        fund_name=fund_name,
                        epoch_start=start_date,
                        epoch_end=end_date,
                        performance_rate=perf_rate,
                        start_balance=start_balance,
                        deposits=inp.deposits_during_period,
                        withdrawals=inp.withdrawals_during_period,
                        profit=profit,
                        end_balance=end_balance,
                        previous_hash=previous_hash,
                    )
                    current_hash = _sha256_hex(payload)

                    row = EpochLedger(
                        internal_client_code=code,
                        fund_name=fund_name,
                        epoch_start=start_date,
                        epoch_end=end_date,
                        performance_rate=perf_rate,
                        start_balance=start_balance,
                        deposits=inp.deposits_during_period,
                        withdrawals=inp.withdrawals_during_period,
                        profit=profit,
                        end_balance=end_balance,
                        previous_hash=previous_hash,
                        current_hash=current_hash,
                    )
                    session.add(row)
                    created_rows.append(row)

                # Flush so we can compute totals and catch constraint errors before reconciliation check
                session.flush()

                # Capital conservation: ensure our accounting equation balances for the period
                # expected_end_total = start_total + deposits - withdrawals + profit
                start_total = sum(
                    (_to_decimal(r.start_balance) for r in created_rows),
                    Decimal("0"),
                )
                deposits_total = sum((_to_decimal(r.deposits) for r in created_rows), Decimal("0"))
                withdrawals_total = sum((_to_decimal(r.withdrawals) for r in created_rows), Decimal("0"))
                profit_total = sum((_to_decimal(r.profit) for r in created_rows), Decimal("0"))
                expected_end_total = _q2(start_total + deposits_total - withdrawals_total + profit_total)

                ledger_total = session.query(func.coalesce(func.sum(EpochLedger.end_balance), 0)).filter(
                    func.lower(EpochLedger.fund_name) == fund_name.lower(),
                    EpochLedger.epoch_start == start_date,
                    EpochLedger.epoch_end == end_date,
                ).scalar()
                ledger_total = _q2(_to_decimal(ledger_total))

                InstitutionalValidationService.validate_capital_conservation(
                    expected_end_total=expected_end_total,
                    actual_end_total=ledger_total,
                    tolerance=Decimal("0.01"),
                )

                diff = _q2(abs(ledger_total - head_total))
                if diff > Decimal("0.01"):
                    raise ValueError(
                        f"Reconciliation failed: ledger_total={ledger_total} vs head_office_total={head_total} (diff={diff}). Difference exceeds $0.01 tolerance."
                    )

            return {
                "fund_id": fund_id,
                "fund_name": fund_name,
                "epoch_start": start_date.isoformat(),
                "epoch_end": end_date.isoformat(),
                "performance_rate": str(perf_rate),
                "investors_processed": len(created_rows),
                "total_profit": float(total_profit),
                "ledger_total_end_balance": float(head_total),  # reconciled to head office total
            }

        except IntegrityError as ie:
            # begin_nested() automatically rolls back the savepoint on exception
            # No need to manually rollback
            raise ValueError(f"Database constraint error while writing epoch ledger: {str(ie.orig)}") from ie

    @classmethod
    def preview_epoch_for_fund(
        cls,
        *,
        fund_id: int,
        start_date: datetime,
        end_date: datetime,
        performance_rate: Decimal | float | str,
        session=None,
    ):
        """
        Dry-run preview for UI: computes total_local_valuation (sum of simulated end balances)
        without writing any EpochLedger rows.
        """
        if session is None:
            session = db.session

        perf_rate = _to_decimal(performance_rate)

        fund = session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            raise ValueError(f"Fund with id {fund_id} not found")

        investor_inputs = cls._build_investor_inputs(
            fund_id=fund_id,
            fund_name=fund.fund_name,
            start_date=start_date,
            end_date=end_date,
            session=session,
        )
        if not investor_inputs:
            raise ValueError("No eligible investments found for this fund in the given period")

        period_days = cls._period_days(start_date, end_date)
        total_weighted = sum((inp.weighted_capital for inp in investor_inputs.values()), Decimal("0"))
        if total_weighted <= 0:
            raise ValueError("Total weighted capital is zero; cannot allocate profit")

        # FLAT MONTH OVERRIDE: If period covers full calendar month (>= 28 days), 
        # apply performance rate as flat multiplier on total capital
        is_full_month = cls._is_full_calendar_month(start_date, end_date)
        
        if is_full_month:
            # Flat rate: total_capital * performance_rate (no day-weighted averaging)
            total_capital = sum(
                (inp.principal_before_start + inp.deposits_during_period 
                 for inp in investor_inputs.values()),
                Decimal("0")
            )
            total_profit = _q2(total_capital * perf_rate)
        else:
            # Pro-rata: average_active_capital * performance_rate (day-weighted)
            avg_active_capital = (total_weighted / Decimal(period_days))
            total_profit = _q2(avg_active_capital * perf_rate)

        simulated_end_total = Decimal("0.00")
        start_total = Decimal("0.00")
        deposits_total = Decimal("0.00")
        withdrawals_total = Decimal("0.00")
        profit_total = Decimal("0.00")

        for code, inp in investor_inputs.items():
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fund.fund_name,
                start_date=start_date,
            )

            start_balance = _q2(prev_end_balance + inp.principal_before_start)
            profit_share = (inp.weighted_capital / total_weighted)
            profit = _q2(total_profit * profit_share)
            end_balance = _q2(start_balance + inp.deposits_during_period - inp.withdrawals_during_period + profit)

            simulated_end_total += end_balance
            start_total += start_balance
            deposits_total += inp.deposits_during_period
            withdrawals_total += inp.withdrawals_during_period
            profit_total += profit

        expected_end_total = _q2(start_total + deposits_total - withdrawals_total + profit_total)

        # For preview, still compute capital conservation status (but do not throw)
        diff_conservation = _q2((expected_end_total - _q2(simulated_end_total)).copy_abs())

        return {
            "fund_id": fund_id,
            "fund_name": fund.fund_name,
            "epoch_start": start_date.isoformat(),
            "epoch_end": end_date.isoformat(),
            "performance_rate": str(perf_rate),
            "investors_processed": len(investor_inputs),
            "total_profit": float(total_profit),
            "total_local_valuation": float(_q2(simulated_end_total)),
            "capital_conservation_diff": float(diff_conservation),
        }

    @classmethod
    def preview_epoch_for_fund_name(
        cls,
        *,
        fund_name: str,
        start_date: datetime,
        end_date: datetime,
        performance_rate: Decimal | float | str,
        session=None,
    ):
        """Consolidated dry-run across ALL batches for a core fund name.

        Returns a batch breakdown so admins can see distribution per batch.
        """
        if session is None:
            session = db.session

        fn = (fund_name or "").strip().lower()
        if not fn:
            raise ValueError("fund_name is required")

        perf_rate = _to_decimal(performance_rate)
        period_days = cls._period_days(start_date, end_date)

        investments = session.query(Investment).filter(func.lower(Investment.fund_name) == fn).all()
        eligible = []
        for inv in investments:
            active_start = cls._active_start(inv)
            if not active_start or active_start >= end_date:
                continue
            eligible.append(inv)

        if not eligible:
            raise ValueError("No eligible investments found for this fund in the given period")

        weighted_rows = []
        total_weighted = Decimal("0")
        total_capital = Decimal("0")

        for inv in eligible:
            active_start = cls._active_start(inv)
            amount = _to_decimal(inv.amount_deposited)
            total_capital += amount

            if active_start < start_date:
                days_active = (end_date - start_date).days
            else:
                days_active = (end_date - active_start).days
            days_active = max(0, min(period_days, days_active))

            weighted = amount * Decimal(days_active)
            total_weighted += weighted
            weighted_rows.append((inv, amount, days_active, weighted))

        if total_weighted <= 0:
            raise ValueError("Total weighted capital is zero; cannot allocate profit")

        # FLAT MONTH OVERRIDE: If period covers full calendar month (>= 28 days), 
        # apply performance rate as flat multiplier on total capital
        is_full_month = cls._is_full_calendar_month(start_date, end_date)
        
        if is_full_month:
            # Flat rate: total_capital * performance_rate (no day-weighted averaging)
            total_profit = _q2(total_capital * perf_rate)
        else:
            # Pro-rata: average_active_capital * performance_rate (day-weighted)
            avg_active_capital = total_weighted / Decimal(period_days)
            total_profit = _q2(avg_active_capital * perf_rate)

        # Allocate profit per investment row (then group by batch)
        by_batch = {}
        for inv, amount, days_active, weighted in weighted_rows:
            share = weighted / total_weighted
            profit = _q2(total_profit * share)

            b = by_batch.get(inv.batch_id)
            if not b:
                batch = session.query(Batch).filter(Batch.id == inv.batch_id).first()
                by_batch[inv.batch_id] = {
                    "batch_id": inv.batch_id,
                    "batch_name": batch.batch_name if batch else f"Batch {inv.batch_id}",
                    "certificate_number": batch.certificate_number if batch else None,
                    "investor_rows": 0,
                    "total_capital": Decimal("0.00"),
                    "total_profit": Decimal("0.00"),
                }
                b = by_batch[inv.batch_id]

            b["investor_rows"] += 1
            b["total_capital"] += amount
            b["total_profit"] += profit

        batch_breakdown = []
        for _, b in sorted(by_batch.items(), key=lambda x: str(x[0])):
            batch_breakdown.append(
                {
                    "batch_id": b["batch_id"],
                    "batch_name": b["batch_name"],
                    "certificate_number": b["certificate_number"],
                    "investor_rows": int(b["investor_rows"]),
                    "total_capital": float(_q2(b["total_capital"])),
                    "total_profit": float(_q2(b["total_profit"])),
                }
            )

        calculated_total = float(_q2(total_capital + total_profit))

        return {
            "fund_name": fn.capitalize(),
            "epoch_start": start_date.isoformat(),
            "epoch_end": end_date.isoformat(),
            "performance_rate": str(perf_rate),
            "period_days": period_days,
            "investor_rows": len(weighted_rows),
            "total_capital": float(_q2(total_capital)),
            "total_profit": float(total_profit),
            "calculated_total": calculated_total,
            "batch_breakdown": batch_breakdown,
        }
