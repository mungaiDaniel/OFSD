"""
Batch-Level Valuation Service

Atomic batch valuations: timeline and principal are scoped to one batch only.
- Deployment date drives prorated months (e.g. Jan 15 → January partial + full months to valuation_date).
- Incremental runs only compound from the day after the previous period_end through valuation_date.
- Withdrawals and investor snapshots are isolated to the batch (join Investment.batch_id).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import calendar

from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased

from app.database.database import db
from app.Investments.model import Investment, Withdrawal, FINAL_WITHDRAWAL_STATUSES
from app.Batch.model import Batch
from app.Valuation.model import BatchValuation, InvestmentBatchValuation


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _utc_date(d: datetime | date) -> date:
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    # Treat business dates as calendar dates; do not timezone-shift day boundaries.
    return d.date()


def _at_day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _at_end_of_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def _month_calendar_days(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _iter_month_segments(range_start: date, range_end: date):
    """
    Yield (seg_start, seg_end, active_days, month_calendar_days) for each calendar month
    overlapping [range_start, range_end] inclusive.
    """
    if range_end < range_start:
        return
    y, m = range_start.year, range_start.month
    while True:
        month_start = date(y, m, 1)
        month_end = date(y, m, _month_calendar_days(y, m))
        seg_start = max(range_start, month_start)
        seg_end = min(range_end, month_end)
        if seg_start <= seg_end:
            active_days = (seg_end - seg_start).days + 1
            month_days = (month_end - month_start).days + 1
            yield seg_start, seg_end, active_days, month_days
        if seg_end >= range_end:
            break
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def _withdrawals_for_batch_window(
    session,
    batch_id: int,
    period_start: datetime,
    period_end: datetime,
) -> tuple[Decimal, dict[str, Decimal]]:
    """
    Sum withdrawals tied to this batch only (same client + batch + fund alignment).
    Returns total and per YYYY-MM bucket for monthly segments.
    """
    Inv = aliased(Investment)
    fund_match = or_(
        and_(Inv.fund_id.isnot(None), Inv.fund_id == Withdrawal.fund_id),
        and_(Inv.fund_id.is_(None), Withdrawal.fund_id.is_(None)),
    )
    rows = (
        session.query(Withdrawal.amount, Withdrawal.date_withdrawn)
        .select_from(Withdrawal)
        .join(
            Inv,
            and_(
                Inv.internal_client_code == Withdrawal.internal_client_code,
                Inv.batch_id == batch_id,
                fund_match,
            ),
        )
        .filter(
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
            Withdrawal.date_withdrawn >= period_start,
            Withdrawal.date_withdrawn <= period_end,
        )
        .all()
    )
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    total = Decimal("0")
    for amount, dt in rows:
        if not dt:
            continue
        wd = _utc_date(dt)
        key = f"{wd.year}-{wd.month:02d}"
        amt = _to_decimal(amount)
        by_month[key] += amt
        total += amt
    return total, by_month


def _compute_starting_balance(
    investments: list[Investment],
    previous_valuation: BatchValuation | None,
) -> Decimal:
    total_net = sum(_to_decimal(inv.net_principal) for inv in investments)
    if not previous_valuation:
        return total_net
    prev_end = previous_valuation.period_end_date
    prev_end_date = _utc_date(prev_end)
    prev_bal = _to_decimal(previous_valuation.balance_at_end_of_period)
    new_principal = Decimal("0")
    for inv in investments:
        if not inv.date_deposited:
            continue
        dep = _utc_date(inv.date_deposited)
        if dep > prev_end_date:
            new_principal += _to_decimal(inv.net_principal)
    return prev_bal + new_principal


def _valuation_window_dates(
    deployment_date: datetime,
    previous_valuation: BatchValuation | None,
    valuation_date: datetime,
) -> tuple[date, date]:
    val_end = _utc_date(valuation_date)
    if not previous_valuation:
        range_start = _utc_date(deployment_date)
        return range_start, val_end
    prev_end = _utc_date(previous_valuation.period_end_date)
    range_start = prev_end + timedelta(days=1)
    return range_start, val_end


def _distribute_pro_rata(
    investments: list[Investment],
    ending_total: Decimal,
) -> list[tuple[Investment, Decimal]]:
    weights = [(inv, _to_decimal(inv.net_principal)) for inv in investments]
    total_w = sum(w for _, w in weights)
    if total_w <= 0:
        return [(inv, Decimal("0")) for inv, _ in weights]
    out: list[tuple[Investment, Decimal]] = []
    remaining = ending_total
    for i, (inv, w) in enumerate(weights):
        if i == len(weights) - 1:
            out.append((inv, _q2(remaining)))
        else:
            share = _q2(ending_total * (w / total_w))
            out.append((inv, share))
            remaining -= share
    return out


class BatchValuationService:
    @staticmethod
    def run_batch_valuation(
        batch_id: int,
        performance_rate: Decimal | float | str,
        valuation_date: datetime,
    ) -> dict:
        session = db.session

        batch = session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise ValueError(f"Batch with id {batch_id} not found")
        if not batch.date_deployed:
            raise ValueError(f"Batch {batch_id} has no deployment date")

        investments = (
            session.query(Investment).filter(Investment.batch_id == batch_id).all()
        )
        if not investments:
            raise ValueError(f"No investments found in batch {batch_id}")

        deployment_date = batch.date_deployed
        if deployment_date.tzinfo is None:
            deployment_date = deployment_date.replace(tzinfo=timezone.utc)

        if valuation_date.tzinfo is None:
            valuation_date = valuation_date.replace(tzinfo=timezone.utc)
        else:
            valuation_date = valuation_date.astimezone(timezone.utc)

        previous_valuation = (
            session.query(BatchValuation)
            .filter(BatchValuation.batch_id == batch_id)
            .order_by(BatchValuation.period_end_date.desc())
            .first()
        )

        range_start_d, range_end_d = _valuation_window_dates(
            deployment_date, previous_valuation, valuation_date
        )
        if range_end_d < range_start_d:
            raise ValueError(
                f"Invalid valuation window for batch {batch_id}: "
                f"{range_start_d} to {range_end_d}"
            )

        starting_balance = _compute_starting_balance(investments, previous_valuation)
        total_net_principal = sum(_to_decimal(inv.net_principal) for inv in investments)

        period_start_dt = _at_day_start(range_start_d)
        period_end_dt = _at_end_of_day(range_end_d)

        total_wd, wd_by_month = _withdrawals_for_batch_window(
            session, batch_id, period_start_dt, period_end_dt
        )

        perf_rate = _to_decimal(performance_rate)
        balance = starting_balance
        months_spanned = 0

        for seg_start, _seg_end, active_days, month_days in _iter_month_segments(
            range_start_d, range_end_d
        ):
            months_spanned += 1
            key = f"{seg_start.year}-{seg_start.month:02d}"
            balance -= wd_by_month.get(key, Decimal("0"))
            if balance < 0:
                balance = Decimal("0")
            factor = perf_rate * (Decimal(active_days) / Decimal(month_days))
            balance = balance * (Decimal("1") + factor)
            balance = _q2(balance)

        ending_balance = balance
        total_profit = ending_balance - starting_balance + total_wd

        # Upsert (batch_id, period_end_date) so backfills are idempotent.
        batch_valuation = (
            session.query(BatchValuation)
            .filter(
                BatchValuation.batch_id == batch_id,
                BatchValuation.period_end_date == valuation_date,
            )
            .first()
        )
        if batch_valuation is None:
            batch_valuation = BatchValuation(
                batch_id=batch_id,
                period_end_date=valuation_date,
                balance_at_end_of_period=ending_balance,
                performance_rate=perf_rate,
                total_principal=total_net_principal,
                total_profit=total_profit,
                total_withdrawals=total_wd,
            )
            session.add(batch_valuation)
            session.flush()
        else:
            batch_valuation.balance_at_end_of_period = ending_balance
            batch_valuation.performance_rate = perf_rate
            batch_valuation.total_principal = total_net_principal
            batch_valuation.total_profit = total_profit
            batch_valuation.total_withdrawals = total_wd

        for inv, bal in _distribute_pro_rata(investments, ending_balance):
            existing = (
                session.query(InvestmentBatchValuation)
                .filter(
                    InvestmentBatchValuation.investment_id == inv.id,
                    InvestmentBatchValuation.batch_id == batch_id,
                    InvestmentBatchValuation.period_end_date == valuation_date,
                )
                .first()
            )
            snap_net = _to_decimal(inv.net_principal)
            if existing:
                existing.balance_at_end_of_period = bal
                existing.net_principal_snapshot = snap_net
                existing.batch_id = batch_id
            else:
                session.add(
                    InvestmentBatchValuation(
                        investment_id=inv.id,
                        batch_id=batch_id,
                        period_end_date=valuation_date,
                        balance_at_end_of_period=bal,
                        net_principal_snapshot=snap_net,
                    )
                )

        session.commit()

        return {
            "batch_id": batch_id,
            "batch_name": batch.batch_name,
            "deployment_date": deployment_date.isoformat(),
            "valuation_date": valuation_date.isoformat(),
            "range_start_date": range_start_d.isoformat(),
            "range_end_date": range_end_d.isoformat(),
            "starting_balance": float(starting_balance),
            "ending_balance": float(ending_balance),
            "total_profit": float(total_profit),
            "performance_rate": float(perf_rate),
            "months_spanned": months_spanned,
            "investor_count": len(investments),
            "total_withdrawals_in_period": float(total_wd),
        }

    @staticmethod
    def get_batch_current_standing(batch_id: int, session=None) -> Decimal:
        """Same standing logic as GET /batches (epoch + statements + batch snapshots)."""
        if session is None:
            session = db.session

        batch = session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return Decimal("0")

        from app.Batch.controllers import BatchController

        return _to_decimal(BatchController._calculate_batch_current_standing(batch, session))
