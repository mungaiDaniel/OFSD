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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import calendar
from dateutil.relativedelta import relativedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from contextlib import nullcontext

from app.database.database import db
from app.Investments.model import (
    Investment,
    Withdrawal,
    EpochLedger,
    FINAL_WITHDRAWAL_STATUSES,
    WITHDRAWAL_STATUS_APPROVED,
    WITHDRAWAL_STATUS_EXECUTED,
)
from app.Batch.core_fund import CoreFund
from app.logic.institutional_validation_service import InstitutionalValidationService
from app.Batch.model import Batch


GENESIS_HASH = "0" * 64


def _get_calendar_days_in_month(year: int, month: int) -> int:
    """Get the number of days in a specific month, accounting for leap years."""
    return calendar.monthrange(year, month)[1]


def _get_valuation_month_days(start_date: datetime) -> int:
    """
    Determine the denominator for pro-rata calculations.
    
    Returns the number of days in the month of start_date.
    This is used for the dynamic denominator in: profit = capital * rate * (days_active / month_days)
    
    Examples:
    - January 15, 2026 → 31 days
    - February 15, 2026 → 28 days
    - February 15, 2024 → 29 days (leap year)
    - March 15, 2026 → 31 days
    """
    return _get_calendar_days_in_month(start_date.year, start_date.month)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ensure_datetime_utc_dt(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_naive_utc(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


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
    active_capital: Decimal
    days_active: int
    period_days: int
    active_ratio: Decimal


class PortfolioValuationService:
    @staticmethod
    def _count_earning_days_in_period(
        *,
        start_date: datetime,
        end_date: datetime,
        fund_is_active: bool,
        batch_deployed_at: datetime | None,
        deposited_at: datetime | None,
    ) -> int:
        """
        Triple-gate daily accrual counter.
        A day earns only when:
          A) fund is active
          B) batch.date_deployed <= day
          C) investment.date_deposited <= day
        """
        if not fund_is_active:
            return 0
        if deposited_at is None or batch_deployed_at is None:
            return 0

        s = start_date.date()
        e = end_date.date()
        dep_day = deposited_at.date()
        deploy_day = batch_deployed_at.date()

        days = 0
        cursor = s
        while cursor <= e:
            if deploy_day <= cursor and dep_day <= cursor:
                days += 1
            cursor += timedelta(days=1)
        return days

    @staticmethod
    def _period_days(start_date: datetime, end_date: datetime) -> int:
        """
        Calculate actual days in period (inclusive of both start and end).
        """
        days = (end_date - start_date).days + 1  # +1 to include both start and end date
        if days <= 0:
            raise ValueError("end_date must be after start_date (at least 1 day)")
        return days

    @staticmethod
    def _months_in_range(start_date: datetime, end_date: datetime) -> float:
        """
        Calendar-aware month multiplier for the period.

        Uses relativedelta so that "almost full" months are treated as full
        months for standard valuation windows.

        Rules (inclusive period semantics assumed elsewhere in the service):
        - 2026-03-01 to 2026-03-31 → 1 month
        - 2026-03-01 to 2026-04-30 → 2 months
          (61 Period Days should scale profit by 2×)
        - 2026-03-01 to 2026-05-31 → 3 months
        """
        # relativedelta treats the end date as the period terminus (non-inclusive
        # of any additional day beyond the same day-of-month), which matches
        # standard calendar reasoning for month windows.
        diff = relativedelta(end_date, start_date)

        # Base whole months from years + months
        total_months = (diff.years * 12) + diff.months

        # If the residual days segment is "almost" a full month, treat it as one.
        # Using 27 as the floor ensures:
        # - 30/31-day months → counted as full when you cover most of the month
        # - 28/29-day February → still counted as full where appropriate
        if diff.days >= 27:
            total_months += 1

        return float(total_months)

    @staticmethod
    def _get_dynamic_denominator(start_date: datetime, end_date: datetime) -> Decimal:
        """
        Calculate the dynamic denominator for pro-rata profit allocation.
        
        Uses the ACTUAL number of days in the period for precise calculations.
        This handles any date range including leap years and February.
        
        Formula: profit = capital * rate * (days_active / period_days)
        
        Examples:
        - March 1-31 (32 days inclusive) → $10,000 × 5% × (32/32) = $500
        - February 1-28 (28 days inclusive, non-leap) → $10,000 × 5% × (28/28) = $500
        - February 1-29 (29 days inclusive, leap year) → $10,000 × 5% × (29/29) = $500
        - March 15-April 15 (32 days inclusive) → $10,000 × 5% × (32/32) = $500
        """
        # Inclusive of both start and end dates (same convention as _period_days)
        days = (end_date - start_date).days + 1
        if days <= 0:
            raise ValueError("end_date must be after start_date")
        return Decimal(days)

    @staticmethod
    def _is_full_calendar_month(start_date: datetime, end_date: datetime) -> bool:
        """
        Determine if the period covers a full calendar month (>= 28 days).
        
        Returns True if:
        1. Period spans >= 28 days
        2. Start is on the 1st of a month AND end is on the last day of a month
        
        This ensures performance_rate is applied as a flat multiplier on total capital
        (no day-weighted averaging) for full-month periods.
        
        Examples:
        - March 1-31, 2026 → True (exact full month, 31 days)
        - February 1-28, 2026 → True (exact full month, 28 days)
        - February 1-29, 2024 → True (leap year full month, 29 days)
        - March 15-April 15, 2026 → True (31 days, span from 15th to 15th)
        - March 15-31, 2026 → False (17 days only, partial month)
        """
        period_days = (end_date - start_date).days
        if period_days < 28:
            return False
        
        # Check if start is on the 1st of a month
        is_start_first = start_date.day == 1
        
        # Check if end is on the last day of its month
        last_day_of_end_month = _get_calendar_days_in_month(end_date.year, end_date.month)
        is_end_last = end_date.day == last_day_of_end_month
        
        # Full month if starts on 1st AND ends on last day of month
        return is_start_first and is_end_last

    @staticmethod
    @staticmethod
    def _ensure_datetime_utc(dt: datetime) -> datetime:
        return _ensure_datetime_utc_dt(dt)

    def _active_start(investment: Investment) -> datetime:
        """
        Capital inception rule:
        active_from_date = max(batch.date_deployed, investment.date_deposited)

        This prevents ghost profit before cash actually landed, while still
        respecting deployment as a minimum activation floor.
        """
        deposited = PortfolioValuationService._ensure_datetime_utc(investment.date_deposited) if investment.date_deposited else None
        batch_deployed = None
        if getattr(investment, "batch", None) and getattr(investment.batch, "date_deployed", None):
            batch_deployed = PortfolioValuationService._ensure_datetime_utc(investment.batch.date_deployed)

        # Primary rule: max(batch.date_deployed, investment.date_deposited)
        if deposited and batch_deployed:
            return deposited if deposited >= batch_deployed else batch_deployed
        if deposited:
            return deposited
        if batch_deployed:
            return batch_deployed

        # Legacy fallback only when both inception sources are missing.
        return PortfolioValuationService._ensure_datetime_utc(investment.date_transferred) if investment.date_transferred else None

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

        # Normalize period dates to UTC so comparisons with DB datetimes are consistent.
        start_date = cls._ensure_datetime_utc(start_date)
        end_date = cls._ensure_datetime_utc(end_date)

        # Ensure we have a normalized fund name for legacy fallbacks
        fund_name = (fund_name or '').strip()

        investments_query = session.query(Investment).filter(
            or_(
                Investment.fund_id == fund_id,
                (Investment.fund_id == None) & (func.lower(Investment.fund_name) == fund_name.lower()),
            )
        ).filter(
            # ── BATCH DATE-GATE (critical fix) ──────────────────────────────────
            # For fresh start: include all deposits on or before end_date
            # For compound (prev epoch exists): ONLY include NEW deposits >= start_date
            # This prevents double-counting old investments already in previous epoch's ending balance
            # ────────────────────────────────────────────────────────────────────
            Investment.date_deposited <= end_date
        )

        investments = investments_query.all()

        # Total days in valuation month for daily accrual denominator (28/29/30/31).
        valuation_month_days = _get_valuation_month_days(start_date)

        # Detect fresh start: no prior epoch ledger exists for this fund
        start_date_naive = _to_naive_utc(start_date)
        has_previous_ledger = (
            session.query(EpochLedger)
            .filter(func.lower(EpochLedger.fund_name) == fund_name.lower())
            .filter(EpochLedger.epoch_end < start_date_naive)
            .first()
            is not None
        )
        is_fresh_start = not has_previous_ledger

        # ✅ CRITICAL FIX: For compound scenarios, filter OUT old investments already in previous epoch
        # Only include investments deposited THIS PERIOD (>= start_date)
        if not is_fresh_start:
            investments = [inv for inv in investments if cls._ensure_datetime_utc(inv.date_deposited) >= start_date]

        # Resolve core fund status once for triple-gate checks.
        core_fund = session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        fund_is_active = bool(core_fund.is_active) if core_fund is not None else False
        

        # Aggregate per investor
        per_code = {}
        for inv in investments:
            active_start = cls._active_start(inv)

            # If the investment has no date set (uploaded without deploy date or historical import),
            # treat it as active from the start of the valuation period instead of skipping it.
            if active_start is None:
                active_start = start_date

            code = inv.internal_client_code
            
            # ✅ CRITICAL FIX FOR COMPOUND GROWTH:
            # For compound valuations, skip old investments (active_start < start_date)
            # because they're already accounted for in previous epoch's end_balance
            # Only include NEW deposits (active_start >= start_date)
            if not is_fresh_start and active_start < start_date:
                continue

            # Eligibility: include any investor whose active_start is on or before the valuation end date.
            if active_start > end_date:
                continue

            code = inv.internal_client_code
            amount = _to_decimal(inv.amount_deposited)

            # Deposits are treated as:
            # - principal_before_start if active_start < start_date
            # - deposits_during_period if start_date <= active_start <= end_date
            if code not in per_code:
                per_code[code] = {
                    "principal_before_start": Decimal("0"),
                    "deposits_during_period": Decimal("0"),
                    "weighted_capital": Decimal("0"),
                    # Sum of per-row weighted contributions before withdrawals.
                    "weighted_amount_pre_withdrawals": Decimal("0"),
                }

            if active_start < start_date:
                per_code[code]["principal_before_start"] += amount
            elif active_start == start_date and is_fresh_start:
                # Fresh start: treat same-day records as opening principal.
                per_code[code]["principal_before_start"] += amount
            else:
                # For all other cases (new deposits in existing fund or fresh start mid-month),
                # treat as deposits during period.
                per_code[code]["deposits_during_period"] += amount

            # Triple-gate daily accrual (fund active + batch deployed + deposit confirmed).
            batch_deployed_at = None
            if getattr(inv, "batch", None) and getattr(inv.batch, "date_deployed", None):
                batch_deployed_at = cls._ensure_datetime_utc(inv.batch.date_deployed)

            deposited_at = cls._ensure_datetime_utc(inv.date_deposited) if inv.date_deposited else None
            row_days_active = cls._count_earning_days_in_period(
                start_date=start_date,
                end_date=end_date,
                fund_is_active=fund_is_active,
                batch_deployed_at=batch_deployed_at,
                deposited_at=deposited_at,
            )
            if row_days_active > 0:
                row_ratio = Decimal(row_days_active) / Decimal(valuation_month_days)
                per_code[code]["weighted_amount_pre_withdrawals"] += amount * row_ratio

        # ─── Withdrawal query (THE CRITICAL FIX) ────────────────────────────────
        # Only fetch withdrawals that are:
        #   1. Status == "Approved"  (not yet Executed/Processed — those are already
        #      embedded in a previous epoch's end_balance and must NOT be subtracted again)
        #   2. Within the current period [start_date, end_date]  (prevents picking up
        #      withdrawals that belong to a future month)
        #
        # Net_Invested_Base = prev_end_balance - sum(Approved withdrawals this period)
        # Total_Profit      = Net_Invested_Base × performance_rate × months
        # ─────────────────────────────────────────────────────────────────────────
        withdrawals_rows = (
            session.query(Withdrawal)
            .filter(
                or_(
                    Withdrawal.fund_id == fund_id,
                    and_(
                        Withdrawal.fund_id.is_(None),
                        func.lower(Withdrawal.fund_name) == fund_name.lower(),
                    ),
                )
            )
            .filter(Withdrawal.status == WITHDRAWAL_STATUS_APPROVED)  # ONLY pending-execution
            .filter(Withdrawal.date_withdrawn >= start_date)           # current period only
            .filter(Withdrawal.date_withdrawn <= end_date)
            .all()
        )
        withdrawals_by_code = {}
        withdrawals_during_period_by_code = {}
        for w in withdrawals_rows:
            amt = _to_decimal(w.amount)
            withdrawals_by_code[w.internal_client_code] = withdrawals_by_code.get(w.internal_client_code, Decimal("0")) + amt
            # All rows are already within [start_date, end_date] by query constraint
            withdrawals_during_period_by_code[w.internal_client_code] = withdrawals_during_period_by_code.get(w.internal_client_code, Decimal("0")) + amt

        result = {}
        
        # ✅ FIX: For compound scenarios, include investors from previous epoch even if no current deposits
        if not is_fresh_start:
            # Get all investor codes from previous epoch's ledger
            # These investors should continue earning even without new deposits
            prev_ledger_entries = (
                session.query(EpochLedger)
                .filter(func.lower(EpochLedger.fund_name) == fund_name.lower())
                .filter(EpochLedger.epoch_end < start_date_naive)
                .order_by(EpochLedger.epoch_end.desc())
                .all()
            )
            
            prev_epoch_investors = {}
            for prev_entry in prev_ledger_entries:
                code = prev_entry.internal_client_code
                if code not in prev_epoch_investors:
                    # Get the most recent entry for this investor
                    prev_epoch_investors[code] = prev_entry
            
            # Add previous epoch investors to per_code
            for code, prev_entry in prev_epoch_investors.items():
                prev_balance = _to_decimal(prev_entry.end_balance)
                
                # Calculate weight for historical balance (assumed deployed and confirmed before start)
                historical_weight_days = cls._count_earning_days_in_period(
                    start_date=start_date,
                    end_date=end_date,
                    fund_is_active=fund_is_active,
                    batch_deployed_at=start_date,  # Historical money is already deployed
                    deposited_at=start_date,       # Historical money is already deposited
                )
                historical_weight_amount = Decimal("0")
                if historical_weight_days > 0:
                    row_ratio = Decimal(historical_weight_days) / Decimal(valuation_month_days)
                    historical_weight_amount = prev_balance * row_ratio

                if code not in per_code:
                    # Investor has no new deposits this period, but has previous balance
                    per_code[code] = {
                        "principal_before_start": prev_balance,
                        "deposits_during_period": Decimal("0"),
                        "weighted_capital": Decimal("0"),
                        "weighted_amount_pre_withdrawals": historical_weight_amount,
                        "_from_previous_epoch": True,
                    }
                else:
                    # Investor HAS new deposits, but we MUST also add their carry-over weight
                    per_code[code]["principal_before_start"] += prev_balance
                    per_code[code]["weighted_amount_pre_withdrawals"] += historical_weight_amount
        
        for code, agg in per_code.items():
            # Active capital = total principal (before + during period) minus all approved withdrawals up to end_date.
            base_capital = agg["principal_before_start"] + agg["deposits_during_period"]
            active_capital = base_capital - withdrawals_by_code.get(code, Decimal("0"))
            if active_capital <= 0:
                continue

            # Scale weighted amount proportionally after withdrawals.
            weighted_pre_wd = agg.get("weighted_amount_pre_withdrawals", Decimal("0"))
            if base_capital > 0:
                agg["weighted_capital"] = weighted_pre_wd * (active_capital / base_capital)
            else:
                agg["weighted_capital"] = Decimal("0")
            
            # ===== CRITICAL FIX: Include all investors with active_capital > 0 =====
            # Previous logic: if agg["weighted_capital"] <= 0: continue
            # This excluded investors who had 0 earning days (row_days_active=0)
            # But those investors still have active capital and should earn the performance rate!
            #
            # The profit allocation loop will set their weight_factor appropriately
            # NEW LOGIC: Set weight_factor = 0 if weighted_capital is 0, but keep them in results
            if agg["weighted_capital"] <= 0:
                weight_factor = Decimal("0")
                days_active = 0
            else:
                weight_factor = agg["weighted_capital"] / active_capital
                days_active = int((weight_factor * Decimal(valuation_month_days)).to_integral_value(rounding=ROUND_HALF_UP))
                days_active = max(1, min(days_active, valuation_month_days))

            result[code] = InvestorPeriodInputs(
                internal_client_code=code,
                principal_before_start=_q2(agg["principal_before_start"]),
                deposits_during_period=_q2(agg["deposits_during_period"]),
                withdrawals_during_period=_q2(withdrawals_during_period_by_code.get(code, Decimal("0"))),
                weighted_capital=agg["weighted_capital"],  # keep high precision until allocation
                active_capital=_q2(active_capital),
                days_active=int(days_active),
                period_days=int(valuation_month_days),
                active_ratio=weight_factor,
            )
        
        
        return result

    @staticmethod
    def _get_previous_epoch_hash_and_end_balance(*, session, internal_client_code: str, fund_name: str, start_date: datetime):
        """
        Returns the latest committed ledger balance strictly BEFORE the valuation start.

        Using `< start_date` (not `<=`) prevents accidentally pulling same-day ledger
        rows into the opening balance when an epoch boundary lands on that date.
        """
        naive_start_date = _to_naive_utc(start_date)
        prev = (
            session.query(EpochLedger)
            .filter(EpochLedger.internal_client_code == internal_client_code)
            .filter(func.lower(EpochLedger.fund_name) == fund_name.lower())
            .filter(EpochLedger.epoch_end < naive_start_date)
            .order_by(EpochLedger.epoch_end.desc(), EpochLedger.id.desc())
            .first()
        )
        if not prev:
            return GENESIS_HASH, Decimal("0.00")
        return prev.current_hash, _to_decimal(prev.end_balance)

    @staticmethod
    def _resolve_epoch_cashflow(*, prev_end_balance: Decimal, principal_before_start: Decimal, deposits_during_period: Decimal):
        """Determine start/deposit values for an epoch.

        - Fresh start (no previous epoch): start_balance = principal_before_start, deposits are new deposits during period.
        - Compound run (previous epoch exists): start_balance = prev_end_balance, deposits are only new deposits during period.
        
        This ensures Reports table shows correct opening balances for all epochs.
        """
        prev_end_balance = _to_decimal(prev_end_balance)
        principal_before_start = _to_decimal(principal_before_start)
        deposits_during_period = _to_decimal(deposits_during_period)

        if prev_end_balance > Decimal("0"):
            # Compound: opening is previous closing, deposits are new cash
            return _q2(prev_end_balance), _q2(deposits_during_period)

        # Fresh start: opening is the principal from Excel, deposits are any new deposits
        return _q2(principal_before_start), _q2(deposits_during_period)

    @classmethod
    def create_epoch_ledger_for_fund(
        cls,
        *,
        fund_id: int,
        start_date: datetime,
        end_date: datetime,
        performance_rate: Decimal | float | str,
        head_office_total: Decimal | float | str,  # kept for API compatibility but not used here
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

        start_date = cls._ensure_datetime_utc(start_date)
        end_date = cls._ensure_datetime_utc(end_date)

        perf_rate = _to_decimal(performance_rate)

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
        months_detected = max(1, int(cls._months_in_range(start_date, end_date)))

        # Total weighted capital (after withdrawal weighting) for the period.
        total_weighted_capital = sum((inp.weighted_capital for inp in investor_inputs.values()), Decimal("0"))
        if total_weighted_capital <= 0:
            raise ValueError("Total weighted capital is zero or negative; cannot allocate profit")

        # Total active capital (after approved withdrawals) for reporting
        total_active_capital = sum((inp.active_capital for inp in investor_inputs.values()), Decimal("0"))

        # Total open capital (deposits + pre-period principal before withdrawals)
        total_open_capital = sum(
            (inp.principal_before_start + inp.deposits_during_period for inp in investor_inputs.values()),
            Decimal("0"),
        )

        # Total approved withdrawals during the epoch
        total_withdrawals = sum((inp.withdrawals_during_period for inp in investor_inputs.values()), Decimal("0"))

        # ============ FIX FOR COMPOUND GROWTH (create_epoch_ledger_for_fund) ============
        # Before calculating profit, fetch previous epoch end_balances and recalculate opening active capital
        # This is CRITICAL for correct multi-epoch valuations
        
        opening_weights_compounded = {}  # Track compounded opening weights
        total_opening_active_capital_compounded = Decimal("0")
        
        for code, inp in investor_inputs.items():
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fund_name,
                start_date=start_date,
            )

            # ✅ KEY FIX: Use resolved cashflow to correctly handle compound growth
            # We start with the resolved cashflow.
            base_start_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                prev_end_balance=prev_end_balance,
                principal_before_start=inp.principal_before_start,
                deposits_during_period=inp.deposits_during_period,
            )

            # THE FIX: Formula: July_Starting_Balance = June_Ending_Balance - Approved_Withdrawals
            # We subtract all 'Approved' withdrawals from the 'Previous_Month_Balance' BEFORE calculating current month interest.
            start_balance = base_start_balance - inp.withdrawals_during_period

            # Active opening capital = opening + deposits (since we already subtracted withdrawals from opening)
            opening_active = _q2(start_balance + deposits_this_epoch)

            # Use investor day-count ratio from _build_investor_inputs.
            opening_weight = opening_active * inp.active_ratio

            opening_weights_compounded[code] = opening_weight
            total_opening_active_capital_compounded += opening_active
        
        # Use the COMPOUNDED opening active capital for profit calculation
        total_active_capital_for_profit = total_opening_active_capital_compounded
        total_weighted_capital_for_allocation = sum(opening_weights_compounded.values(), Decimal("0"))
        
        # ===== CRITICAL FIX: Use total active capital, not weighted capital, for profit base =====
        # The performance rate should be applied to ALL active capital in the period
        # Weighted capital (based on days_active) should only be used for pro-rata ALLOCATION of profit
        # But the total profit pool should be based on total active capital
        if total_weighted_capital_for_allocation <= 0:
            # All investors have zero weight (unlikely but handle it)
            total_weighted_capital_for_allocation = total_opening_active_capital_compounded or Decimal("1")
        
        # ===== FIX: Correct Profit Calculation with Compound Interest =====
        # Formula: profit = principal * ((1 + rate)^periods - 1)
        # For a single-period valuation, this reduces to profit = principal * rate.
        # The service receives `performance_rate` as a decimal fraction
        # (e.g. 0.0348 for 3.48%).
        # Use total_opening_active_capital_compounded as the profit base
        rate_fraction = perf_rate
        
        # Compound interest formula: (1 + rate)^periods
        compound_factor = (Decimal("1") + rate_fraction) ** months_detected
        total_profit = _q2(total_opening_active_capital_compounded * (compound_factor - Decimal("1")))
        # ====================================================================



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

                    # ✅ KEY FIX: Use resolved cashflow for consistency
                    base_start_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                        prev_end_balance=prev_end_balance,
                        principal_before_start=inp.principal_before_start,
                        deposits_during_period=inp.deposits_during_period,
                    )

                    # Formula: July_Starting_Balance = June_Ending_Balance - Approved_Withdrawals
                    start_balance = base_start_balance - inp.withdrawals_during_period


                    # Validate negative balance due to withdrawals
                    pre_profit_balance = start_balance + deposits_this_epoch
                    if pre_profit_balance < Decimal("0"):
                        raise ValueError(
                            f"Negative balance for {code} after withdrawals: {pre_profit_balance}. "
                            "Ensure withdrawals do not exceed available capital."
                        )

                    # Step B: pro-rata profit (based on compounded weighted capital share)
                    profit_share = (opening_weights_compounded.get(code, Decimal("0")) / total_weighted_capital_for_allocation)
                    profit = _q2(total_profit * profit_share)

                    end_balance = _q2(pre_profit_balance + profit)

                    payload = _ledger_hash_payload(
                        internal_client_code=code,
                        fund_name=fund_name,
                        epoch_start=start_date,
                        epoch_end=end_date,
                        performance_rate=perf_rate,
                        start_balance=start_balance,
                        deposits=deposits_this_epoch,
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
                        deposits=deposits_this_epoch,
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
                # Formula: start_total (which already has withdrawals subtracted) + deposits + profit
                start_total = sum(
                    (_to_decimal(r.start_balance) for r in created_rows),
                    Decimal("0"),
                )
                deposits_total = sum((_to_decimal(r.deposits) for r in created_rows), Decimal("0"))
                withdrawals_total = sum((_to_decimal(r.withdrawals) for r in created_rows), Decimal("0"))
                profit_total = sum((_to_decimal(r.profit) for r in created_rows), Decimal("0"))
                expected_end_total = _q2(start_total + deposits_total + profit_total)

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

            return {
                "fund_id": fund_id,
                "fund_name": fund_name,
                "epoch_start": start_date.isoformat(),
                "epoch_end": end_date.isoformat(),
                "performance_rate": str(perf_rate),
                "investors_processed": len(created_rows),
                "total_profit": float(total_profit),
                # Fund-wide ending balance for this epoch (used for reporting)
                "total_local_valuation": float(ledger_total),
                "ledger_total_end_balance": float(ledger_total),
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

        start_date = cls._ensure_datetime_utc(start_date)
        end_date = cls._ensure_datetime_utc(end_date)

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
        months_detected = max(1, int(cls._months_in_range(start_date, end_date)))

        # Total weighted capital (after withdrawal weighting) for the period.
        total_weighted_capital = sum((inp.weighted_capital for inp in investor_inputs.values()), Decimal("0"))
        if total_weighted_capital <= 0:
            raise ValueError("Total weighted capital is zero or negative; cannot allocate profit")

        # Total active capital (after all approved withdrawals up to end_date) for the period.
        total_active_capital = sum((inp.active_capital for inp in investor_inputs.values()), Decimal("0"))

        # Total open capital (deposits + pre-period principal before withdrawals)
        total_open_capital = sum(
            (inp.principal_before_start + inp.deposits_during_period for inp in investor_inputs.values()),
            Decimal("0"),
        )

        # Total approved withdrawals during the period
        total_withdrawals = sum((inp.withdrawals_during_period for inp in investor_inputs.values()), Decimal("0"))

        # ============ FIX FOR COMPOUND GROWTH ============
        # Before calculating profit, we need to fetch previous epoch end_balances for each investor
        # and recalculate the opening active capital including compound growth
        # This is CRITICAL for correct multi-epoch valuations
        
        opening_weights_compounded = {}  # Track compounded opening weights
        total_opening_active_capital_compounded = Decimal("0")
        
        for code, inp in investor_inputs.items():
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fund.fund_name,
                start_date=start_date,
            )

            # ✅ KEY FIX: Use resolved cashflow to correctly handle compound growth
            base_opening_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                prev_end_balance=prev_end_balance,
                principal_before_start=inp.principal_before_start,
                deposits_during_period=inp.deposits_during_period,
            )

            # Formula: July_Starting_Balance = June_Ending_Balance - Approved_Withdrawals
            opening_balance = base_opening_balance - inp.withdrawals_during_period

            # Active opening capital = opening + deposits
            opening_active = _q2(opening_balance + deposits_this_epoch)

            # Use investor day-count ratio from _build_investor_inputs.
            opening_weight = opening_active * inp.active_ratio

            opening_weights_compounded[code] = opening_weight
            total_opening_active_capital_compounded += opening_active
        
        # Use the COMPOUNDED opening active capital for profit calculation
        # This ensures profit is calculated on the actual available funds (including previous epoch gains)
        total_active_capital_for_profit = total_opening_active_capital_compounded
        total_weighted_capital_for_allocation = sum(opening_weights_compounded.values(), Decimal("0"))
        
        # ===== CRITICAL FIX: Use total active capital, not weighted capital, for profit base =====
        # The performance rate should be applied to ALL active capital in the period
        # Weighted capital (based on days_active) should only be used for pro-rata ALLOCATION of profit
        # But the total profit pool should be based on total active capital
        # Use total_opening_active_capital_compounded as the profit base
        if total_weighted_capital_for_allocation <= 0:
            # All investors have zero weight (unlikely but handle it)
            total_weighted_capital_for_allocation = total_opening_active_capital_compounded or Decimal("1")
        
        # ===== FIX: Correct Profit Calculation with Compound Interest =====
        # Formula: profit = principal * ((1 + rate)^periods - 1)
        # The service receives `performance_rate` as a decimal fraction
        # (e.g. 0.0348 for 3.48%).
        # Use total_opening_active_capital_compounded as the base, not total_weighted_capital_for_allocation
        rate_fraction = perf_rate
        
        # Compound interest formula for multiple periods
        compound_factor = (Decimal("1") + rate_fraction) ** months_detected
        total_profit = _q2(total_opening_active_capital_compounded * (compound_factor - Decimal("1")))
        # ====================================================================
        
        avg_active_capital = total_active_capital_for_profit

        simulated_end_total = Decimal("0.00")
        start_total = Decimal("0.00")
        deposits_total = Decimal("0.00")
        withdrawals_total = Decimal("0.00")
        profit_total = Decimal("0.00")

        investor_breakdown = []

        for code, inp in investor_inputs.items():
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fund.fund_name,
                start_date=start_date,
            )

            # ✅ KEY FIX: Use resolved cashflow for consistency
            base_start_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                prev_end_balance=prev_end_balance,
                principal_before_start=inp.principal_before_start,
                deposits_during_period=inp.deposits_during_period,
            )

            # Formula: July_Starting_Balance = June_Ending_Balance - Approved_Withdrawals
            start_balance = base_start_balance - inp.withdrawals_during_period

            # Validate negative balance due to withdrawals
            pre_profit_balance = start_balance + deposits_this_epoch
            if pre_profit_balance < Decimal("0"):
                raise ValueError(
                    f"Negative balance for {code} after withdrawals: {pre_profit_balance}. "
                    "Ensure withdrawals do not exceed available capital."
                )

            # Allocate profit based on compounded weighted capital
            profit_share = (opening_weights_compounded.get(code, Decimal("0")) / total_weighted_capital_for_allocation)
            profit = _q2(total_profit * profit_share)
            end_balance = _q2(pre_profit_balance + profit)

            simulated_end_total += end_balance
            start_total += start_balance
            deposits_total += deposits_this_epoch
            withdrawals_total += inp.withdrawals_during_period
            profit_total += profit

            investor_breakdown.append(
                {
                    "internal_client_code": code,
                    "principal_before_start": float(inp.principal_before_start),
                    "deposits_during_period": float(deposits_this_epoch),
                    "withdrawals_during_period": float(inp.withdrawals_during_period),
                    "active_capital": float(_q2(start_balance + deposits_this_epoch)),
                    "weighted_capital": float(_q2(opening_weights_compounded.get(code, Decimal("0")))),
                    "profit_share": float(_q2(profit_share * 100)),
                    "days_active": int(inp.days_active),
                    "period_days": int(inp.period_days),
                    "active_ratio_pct": float(_q2(inp.active_ratio * Decimal("100"))),
                    "profit": float(profit),
                    "end_balance": float(end_balance),
                }
            )

        expected_end_total = _q2(start_total + deposits_total + profit_total)

        # For preview, still compute capital conservation status (but do not throw)
        diff_conservation = _q2((expected_end_total - _q2(simulated_end_total)).copy_abs())

        # Expected closing AUM (what actually remains in the fund after withdrawals
        # and this period's profit). This excludes withdrawn cash.
        # Use start_total (which includes compounding) as the base
        expected_closing_aum = _q2(start_total + deposits_total - withdrawals_total + total_profit)

        # Reconciliation total optionally includes period withdrawals so that
        # head office figures that still count cash paid out during the period
        # can be matched without changing AUM semantics.
        reconciliation_total = _q2(expected_closing_aum + total_withdrawals)

        # Nina Simone rule: Distinct investors by email (or name fallback)
        investor_codes = list(investor_inputs.keys())
        investor_rows = (
            session.query(Investment)
            .filter(Investment.fund_id == fund_id)
            .filter(Investment.internal_client_code.in_(investor_codes))
            .all()
        )
        distinct_investor_emails = {
            inv.investor_email.strip().lower() for inv in investor_rows if inv.investor_email
        }
        if not distinct_investor_emails:
            distinct_investor_emails = {
                inv.investor_name.strip().lower() for inv in investor_rows if inv.investor_name
            }

        projected_portfolio_value = _q2(total_active_capital_for_profit + total_profit)

        return {
            "fund_id": fund_id,
            "fund_name": fund.fund_name,
            "epoch_start": start_date.isoformat(),
            "epoch_end": end_date.isoformat(),
            "performance_rate": str(perf_rate),
            "period_days": period_days,
            "months_detected": months_detected,
            "withdrawals_applied": float(total_withdrawals),
            "total_rows_detected": len(investor_inputs),
            "investors_processed": len(investor_inputs),
            "distinct_investor_count": len(distinct_investor_emails),
            "gross_principal": float(_q2(total_active_capital_for_profit)),
            "excel_total": float(_q2(total_active_capital_for_profit + total_withdrawals)),
            "withdrawals_total": float(_q2(total_withdrawals)),
            "net_excel_total": float(_q2(total_active_capital_for_profit)),
            "performance_applied": float(_q2(total_profit)),
            "projected_portfolio_value": float(projected_portfolio_value),
            "total_open_capital": float(_q2(total_active_capital_for_profit + total_withdrawals)),
            "total_start_balance": float(_q2(start_total)),  # Opening balance with compound growth (0 for fresh start members)
            "total_deposits": float(_q2(deposits_total)),
            "total_withdrawals": float(_q2(total_withdrawals)),
            "total_capital": float(_q2(total_active_capital_for_profit)),
            "total_active_capital": float(_q2(total_active_capital_for_profit)),
            "total_weighted_capital": float(_q2(total_weighted_capital_for_allocation)),
            "average_active_capital": float(_q2(avg_active_capital)),
            "total_profit": float(total_profit),
            # Current AUM = active capital (after withdrawals)
            "current_aum": float(_q2(total_active_capital_for_profit)),
            # Expected closing AUM (fund NAV excluding withdrawn cash)
            "expected_closing_aum": float(expected_closing_aum),
            # Reconciliation total = expected closing AUM + withdrawals during period
            "reconciliation_total": float(reconciliation_total),
            # Historical simulated end total (kept for diagnostics)
            "total_local_valuation": float(_q2(simulated_end_total)),
            "capital_conservation_diff": float(diff_conservation),
            "calculation": {
                "formula": "profit = total_active_capital (with compound growth) * performance_rate * months_detected",
                "total_active_capital": float(_q2(total_active_capital_for_profit)),
                "months_detected": months_detected,
                "performance_rate": float(perf_rate),
                "total_profit": float(total_profit),
            },
            # Compatibility alias used by endpoint-level reconciliation
            "total_closing_aum": float(expected_closing_aum),
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

        start_date = cls._ensure_datetime_utc(start_date)
        end_date = cls._ensure_datetime_utc(end_date)

        fn = (fund_name or "").strip().lower()
        if not fn:
            raise ValueError("fund_name is required")

        perf_rate = _to_decimal(performance_rate)
        months = cls._months_in_range(start_date, end_date)

        # Get core fund for fund_id
        core = session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == fn).first()
        if not core:
            raise ValueError(f"Fund '{fn}' not found")

        # Use the same investor input logic as fund_id path (includes approved withdrawals + weighting)
        investor_inputs = cls._build_investor_inputs(
            fund_id=core.id,
            fund_name=fn,
            start_date=start_date,
            end_date=end_date,
            session=session,
        )

        if not investor_inputs:
            raise ValueError("No eligible investments found for this fund in the given period")

        # For reporting in the UI
        months_detected = max(1, int(cls._months_in_range(start_date, end_date)))
        period_days = cls._period_days(start_date, end_date)

        total_weighted_capital = sum((inp.weighted_capital for inp in investor_inputs.values()), Decimal("0"))
        total_active_capital = sum((inp.active_capital for inp in investor_inputs.values()), Decimal("0"))
        total_open_capital = sum(
            (inp.principal_before_start + inp.deposits_during_period for inp in investor_inputs.values()),
            Decimal("0"),
        )
        total_withdrawals = sum((inp.withdrawals_during_period for inp in investor_inputs.values()), Decimal("0"))

        if total_weighted_capital <= 0:
            raise ValueError("Total weighted capital is zero or negative; cannot allocate profit")

        # ============ FIX FOR COMPOUND GROWTH (preview_epoch_for_fund_name) ============
        # Before calculating profit, fetch previous epoch end_balances and recalculate opening active capital
        opening_weights_compounded = {}
        total_opening_active_capital_compounded = Decimal("0")
        period_days = cls._period_days(start_date, end_date)
        
        for code, inp in investor_inputs.items():
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fn,
                start_date=start_date,
            )
            
            # ✅ KEY FIX: Use resolved cashflow to correctly handle compound growth
            opening_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                prev_end_balance=prev_end_balance,
                principal_before_start=inp.principal_before_start,
                deposits_during_period=inp.deposits_during_period,
            )
            
            # ✅ Active capital = opening_balance + deposits_this_epoch - withdrawals
            # This ensures second month starts with first month's ending balance
            opening_active = _q2(opening_balance + deposits_this_epoch - inp.withdrawals_during_period)
            
            opening_weight = opening_active * inp.active_ratio
            
            opening_weights_compounded[code] = opening_weight
            total_opening_active_capital_compounded += opening_active
        
        total_active_capital_for_profit = total_opening_active_capital_compounded
        total_weighted_capital_for_allocation = sum(opening_weights_compounded.values(), Decimal("0"))


        if total_weighted_capital_for_allocation <= 0:
            total_weighted_capital_for_allocation = total_opening_active_capital_compounded or Decimal("1")
        
        # ===== CRITICAL FIX: Use total active capital, not weighted capital, for profit base =====
        # The performance rate should be applied to ALL active capital in the period
        # Weighted capital (based on days_active) should only be used for pro-rata ALLOCATION of profit
        # But the total profit pool should be based on total active capital
        
        # ===== FIX: Correct Profit Calculation with Compound Interest =====
        # Formula: profit = principal * ((1 + rate)^periods - 1)
        # The service receives `performance_rate` as a decimal fraction
        # (e.g. 0.0348 for 3.48%).
        # Use total_opening_active_capital_compounded as the profit base
        rate_fraction = perf_rate
        
        # Compound interest formula for multiple periods
        compound_factor = (Decimal("1") + rate_fraction) ** months_detected
        total_profit = _q2(total_opening_active_capital_compounded * (compound_factor - Decimal("1")))
        # ====================================================================
        
        avg_active_capital = total_active_capital_for_profit

        # ================================================

        # Calculate totals for reconciliation validation
        total_start_balance = Decimal("0")
        total_deposits = Decimal("0")
        for code, inp in investor_inputs.items():
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fn,
                start_date=start_date,
            )
            # ✅ Use SAME resolved cashflow logic for consistency
            opening_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                prev_end_balance=prev_end_balance,
                principal_before_start=inp.principal_before_start,
                deposits_during_period=inp.deposits_during_period,
            )
            total_start_balance += opening_balance
            total_deposits += deposits_this_epoch

        # Determine batch allocation per investor code across all investments.
        # This preserves multi-batch holdings for clients with positions in more than one batch.
        inv_rows = (
            session.query(Investment)
            .filter(Investment.fund_id == core.id, Investment.internal_client_code.in_(list(investor_inputs.keys())))
            .all()
        )

        code_batch_amounts: dict[str, dict[int, Decimal]] = {}
        for inv in inv_rows:
            if inv.batch_id is None:
                continue
            code = inv.internal_client_code
            code_batch_amounts.setdefault(code, {})
            code_batch_amounts[code][inv.batch_id] = code_batch_amounts[code].get(inv.batch_id, Decimal("0")) + _to_decimal(inv.amount_deposited)

        # Aggregate by batch using the investor's weighted capital split by batch share.
        by_batch = {}
        for code, inp in investor_inputs.items():
            batch_amounts = code_batch_amounts.get(code)
            if not batch_amounts:
                continue

            total_amount = sum(batch_amounts.values(), Decimal("0"))
            if total_amount <= 0:
                continue

            for batch_id, amount in batch_amounts.items():
                share = amount / total_amount
                if share <= 0:
                    continue

                b = by_batch.get(batch_id)
                if not b:
                    batch = session.query(Batch).filter(Batch.id == batch_id).first()
                    by_batch[batch_id] = {
                        "batch_id": batch_id,
                        "batch_name": batch.batch_name if batch else f"Batch {batch_id}",
                        "certificate_number": batch.certificate_number if batch else None,
                        "investor_rows": 0,
                        "total_weighted_capital": Decimal("0"),
                    }
                    b = by_batch[batch_id]

                b["investor_rows"] += 1
                b["total_weighted_capital"] += _q2(opening_weights_compounded.get(code, Decimal("0")) * share)

        total_batch_capital = sum(b["total_weighted_capital"] for b in by_batch.values())
        batch_breakdown = []
        for _, b in sorted(by_batch.items(), key=lambda x: str(x[0])):
            if total_batch_capital > 0:
                share = b["total_weighted_capital"] / total_batch_capital
                batch_profit = _q2(total_profit * share)
            else:
                batch_profit = Decimal("0.00")
            batch_breakdown.append(
                {
                    "batch_id": b["batch_id"],
                    "batch_name": b["batch_name"],
                    "certificate_number": b["certificate_number"],
                    "investor_rows": int(b["investor_rows"]),
                    "total_capital": float(_q2(b["total_weighted_capital"])),
                    "total_profit": float(batch_profit),
                }
            )

        expected_closing_aum = _q2(total_active_capital_for_profit + total_profit)
        reconciliation_total = _q2(expected_closing_aum + total_withdrawals)
        calculated_total = float(reconciliation_total)

        investor_breakdown = []
        for code, inp in investor_inputs.items():
            # For display, we need to show the COMPOUNDED opening balance, not original principal
            _, prev_end_balance = cls._get_previous_epoch_hash_and_end_balance(
                session=session,
                internal_client_code=code,
                fund_name=fn,
                start_date=start_date,
            )

            # ✅ Use resolved cashflow for consistency
            opening_balance, deposits_this_epoch = cls._resolve_epoch_cashflow(
                prev_end_balance=prev_end_balance,
                principal_before_start=inp.principal_before_start,
                deposits_during_period=inp.deposits_during_period,
            )

            # ✅ Compounded active capital uses resolved values
            compounded_active = _q2(opening_balance + deposits_this_epoch - inp.withdrawals_during_period)
            profit_share = (opening_weights_compounded.get(code, Decimal("0")) / total_weighted_capital_for_allocation)
            profit = _q2(total_profit * profit_share)

            investor_breakdown.append(
                {
                    "internal_client_code": code,
                    "principal_before_start": float(inp.principal_before_start),
                    "deposits_during_period": float(deposits_this_epoch),  # ✅ Use resolved deposits
                    "withdrawals_during_period": float(inp.withdrawals_during_period),
                    "active_capital": float(compounded_active),
                    "weighted_capital": float(_q2(opening_weights_compounded.get(code, Decimal("0")))),
                    "profit_share": float(_q2(profit_share * 100)),
                    "days_active": int(inp.days_active),
                    "period_days": int(inp.period_days),
                    "active_ratio_pct": float(_q2(inp.active_ratio * Decimal("100"))),
                    "profit": float(profit),
                }
            )

        distinct_investor_emails = {
            inv.investor_email.strip().lower() for inv in inv_rows if inv.investor_email
        }
        if not distinct_investor_emails:
            distinct_investor_emails = {
                inv.investor_name.strip().lower() for inv in inv_rows if inv.investor_name
            }

        projected_portfolio_value = _q2(total_active_capital_for_profit + total_profit)

        return {
            "fund_name": fn.capitalize(),
            "epoch_start": start_date.isoformat(),
            "epoch_end": end_date.isoformat(),
            "performance_rate": str(perf_rate),
            "period_days": period_days,
            "months_detected": months_detected,
            "withdrawals_applied": float(total_withdrawals),
            "total_rows_detected": len(investor_inputs),
            "investor_rows": len(investor_inputs),
            "distinct_investor_count": len(distinct_investor_emails),
            "gross_principal": float(_q2(total_active_capital_for_profit)),
            "excel_total": float(_q2(total_active_capital_for_profit + total_withdrawals)),
            "withdrawals_total": float(_q2(total_withdrawals)),
            "net_excel_total": float(_q2(total_active_capital_for_profit)),
            "performance_applied": float(_q2(total_profit)),
            "projected_portfolio_value": float(projected_portfolio_value),
            "total_open_capital": float(_q2(total_active_capital_for_profit + total_withdrawals)),
            "total_capital": float(_q2(total_active_capital_for_profit)),
            "total_active_capital": float(_q2(total_active_capital_for_profit)),
            "total_weighted_capital": float(_q2(total_weighted_capital_for_allocation)),
            "average_active_capital": float(_q2(avg_active_capital)),
            "total_profit": float(total_profit),
            # Current AUM = active capital (after withdrawals)
            "current_aum": float(_q2(total_active_capital_for_profit)),
            # Expected closing AUM (fund NAV excluding withdrawn cash)
            "expected_closing_aum": float(expected_closing_aum),
            # Reconciliation total = expected closing AUM + withdrawals during period
            "reconciliation_total": float(reconciliation_total),
            "total_closing_aum": float(expected_closing_aum),
            "total_start_balance": float(_q2(total_start_balance)),
            "total_deposits": float(_q2(total_deposits)),
            "total_withdrawals": float(_q2(total_withdrawals)),
            "detected_principal": float(_q2(total_deposits)),
            "calculated_profit": float(total_profit),
            "total_to_commit": float(expected_closing_aum),
            "calculated_total": calculated_total,
            "batch_breakdown": batch_breakdown,
            "calculation": {
                "formula": "profit = total_active_capital (with compound growth) * performance_rate * months_detected",
                "total_active_capital": float(_q2(total_active_capital_for_profit)),
                "months_detected": months_detected,
                "performance_rate": float(perf_rate),
                "total_profit": float(total_profit),
            },
            "investor_breakdown": investor_breakdown,
        }