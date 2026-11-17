"""
Unit-based redemptions for NAV funds (e.g. Janus Henderson, Axiom).

A transfer agent books a redemption in SHARES: e.g. Janus contract note
"101.423 shares of Horizon Biotechnology A2 USD at NAV 37.96 = USD 3,850.00,
trade date 20/10/2026". Recording it the same way keeps our records in line
with theirs: executing the redemption reduces the client's InvestorShares, so
from then on value = remaining shares x NAV, exactly as at the transfer agent.

Legacy withdrawals (cash only, shares_redeemed NULL) are untouched and keep
being subtracted as cash wherever they always were. A unit redemption is
excluded from those cash subtractions (CASH_WITHDRAWAL_FILTER), because the
shares already went down — subtracting the cash too would double-count.

On execute:
  1. Shares are taken from the client's holdings in this fund/class, oldest
     deployment first (FIFO), and each lot touched is recorded in
     withdrawal_lots (auditable; one statement row per lot).
  2. InvestorShares.shares_owned, Investment.shares_owned and
     Batch.total_shares are reduced together (same three counts
     switch_correction keeps in step). A lot that reaches 0 is deactivated.
  3. Valuation snapshots for those lots dated on/after the trade date are
     corrected to the reduced share count, and a snapshot is written at the
     trade date at the redemption NAV, so every "latest snapshot" figure is
     post-redemption straight away (no gap until the next valuation run).
  4. The withdrawal is marked Executed with gross = contract-note amount,
     net = gross - exit fee.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from app.database.database import db
from app.Investments.model import (
    Investment,
    Withdrawal,
    WithdrawalLot,
    WITHDRAWAL_STATUS_APPROVED,
    WITHDRAWAL_STATUS_EXECUTED,
    WITHDRAWAL_STATUS_PENDING,
)

SHARE_Q = Decimal("0.000001")
CENT = Decimal("0.01")


class RedemptionError(ValueError):
    pass


def _dec(value, field):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RedemptionError(f"{field} must be a number")
    return d


def _date(value, field, required=True):
    if value in (None, ""):
        if required:
            raise RedemptionError(f"{field} is required")
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")[:10]).date()
    except ValueError:
        raise RedemptionError(f"{field} must be a date (YYYY-MM-DD)")


def client_lots(session, client_code, fund_id, share_class_id=None):
    """The client's active holdings in this fund (optionally one class), oldest deployment first."""
    from app.Funds.investor_shares import InvestorShares

    q = (
        session.query(InvestorShares, Investment)
        .join(Investment, InvestorShares.investment_id == Investment.id)
        .filter(
            func.lower(Investment.internal_client_code) == func.lower(str(client_code)),
            Investment.fund_id == fund_id,
            InvestorShares.is_active.is_(True),
            InvestorShares.shares_owned > 0,
        )
    )
    if share_class_id is not None:
        q = q.filter(InvestorShares.share_class_id == share_class_id)
    return q.order_by(InvestorShares.deployment_date.asc(), InvestorShares.id.asc()).all()


def execute_redemption(
    session,
    *,
    client_code,
    fund_id,
    shares,
    nav,
    trade_date,
    share_class_id=None,
    gross_amount=None,
    exit_fee=0,
    settlement_date=None,
    ta_reference=None,
    note=None,
    withdrawal=None,
):
    """
    Record and execute a unit redemption. `withdrawal` may be an existing
    Pending/Approved cash request being fulfilled; otherwise a new Withdrawal
    row is created. Commits on success. Returns the Withdrawal.
    """
    from app.Batch.core_fund import CoreFund
    from app.Batch.model import Batch
    from app.Funds.investor_shares import InvestorShares
    from app.Valuation.valuation_snapshot import ValuationSnapshot

    shares = _dec(shares, "shares").quantize(SHARE_Q)
    nav = _dec(nav, "nav")
    exit_fee = _dec(exit_fee or 0, "exit_fee").quantize(CENT)
    trade_date = _date(trade_date, "trade_date")
    settlement_date = _date(settlement_date, "settlement_date", required=False)
    if shares <= 0:
        raise RedemptionError("shares must be greater than zero")
    if nav <= 0:
        raise RedemptionError("nav must be greater than zero")
    if exit_fee < 0:
        raise RedemptionError("exit_fee cannot be negative")

    computed_gross = (shares * nav).quantize(CENT)
    if gross_amount in (None, ""):
        gross = computed_gross
    else:
        gross = _dec(gross_amount, "gross_amount").quantize(CENT)
        # Transfer agents round shares, so shares x NAV can differ from the
        # contract-note amount by a few cents (101.423 x 37.96 = 3,850.02 vs
        # 3,850.00). Anything bigger means a typo in shares, NAV or amount.
        tolerance = max(Decimal("1.00"), computed_gross * Decimal("0.001"))
        if abs(gross - computed_gross) > tolerance:
            raise RedemptionError(
                f"gross_amount {gross:,.2f} doesn't match shares x NAV ({computed_gross:,.2f}); check the contract note"
            )
    if exit_fee > gross:
        raise RedemptionError("exit_fee cannot exceed the gross amount")

    fund = session.get(CoreFund, fund_id) if fund_id is not None else None
    if fund is None:
        raise RedemptionError("fund not found")

    if withdrawal is not None:
        if withdrawal.shares_redeemed is not None:
            raise RedemptionError("this withdrawal has already been executed as a redemption")
        if withdrawal.status not in (WITHDRAWAL_STATUS_PENDING, WITHDRAWAL_STATUS_APPROVED):
            raise RedemptionError(f"a {withdrawal.status} withdrawal can't be executed")
        if str(withdrawal.internal_client_code).lower() != str(client_code).lower():
            raise RedemptionError("client does not match the withdrawal")

    lots = client_lots(session, client_code, fund.id, share_class_id)
    if not lots:
        raise RedemptionError("client has no active holding in this fund" + (" / share class" if share_class_id else ""))
    classes = {h.share_class_id for h, _ in lots}
    if share_class_id is None and len(classes) > 1:
        raise RedemptionError("client holds more than one share class in this fund; choose the share class")
    share_class_id = share_class_id if share_class_id is not None else next(iter(classes))

    available = sum((Decimal(str(h.shares_owned)) for h, _ in lots), Decimal("0"))
    if shares > available:
        raise RedemptionError(f"client only holds {available:,.6f} shares in this class; cannot redeem {shares:,.6f}")

    now = datetime.now(timezone.utc)
    if withdrawal is None:
        withdrawal = Withdrawal(internal_client_code=lots[0][1].internal_client_code)
        session.add(withdrawal)
    withdrawal.fund_id = fund.id
    withdrawal.fund_name = fund.fund_name
    withdrawal.share_class_id = share_class_id
    withdrawal.shares_redeemed = shares
    withdrawal.redemption_nav = nav
    withdrawal.trade_date = trade_date
    withdrawal.settlement_date = settlement_date
    withdrawal.ta_reference = (str(ta_reference).strip() or None) if ta_reference else None
    withdrawal.gross_amount = gross
    withdrawal.exit_fee_deducted = exit_fee
    withdrawal.amount = gross - exit_fee
    withdrawal.date_withdrawn = datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc)
    withdrawal.status = WITHDRAWAL_STATUS_EXECUTED
    withdrawal.approved_at = withdrawal.approved_at or now.replace(tzinfo=None)
    withdrawal.executed_at = now
    if note:
        withdrawal.note = str(note)[:255]
    session.flush()

    remaining = shares
    touched_batch_ids = set()
    for holding, inv in lots:
        if remaining <= 0:
            break
        before = Decimal(str(holding.shares_owned))
        take = min(before, remaining)
        after = (before - take).quantize(SHARE_Q)
        remaining -= take

        session.add(WithdrawalLot(
            withdrawal_id=withdrawal.id, investor_shares_id=holding.id, investment_id=inv.id,
            batch_id=holding.batch_id or inv.batch_id, shares_redeemed=take, shares_before=before,
            deployment_nav=holding.deployment_nav,
        ))

        holding.shares_owned = after
        if after == 0:
            holding.is_active = False
        inv.shares_owned = (Decimal(str(inv.shares_owned or before)) - take).quantize(Decimal("0.0001"))
        batch = session.get(Batch, holding.batch_id or inv.batch_id)
        if batch is not None and batch.total_shares is not None:
            batch.total_shares = max(Decimal("0"), Decimal(str(batch.total_shares)) - take)
            touched_batch_ids.add(batch.id)

        # Snapshots on/after the trade date were valued with the old share
        # count — correct them, then make sure one exists AT the trade date.
        later = session.query(ValuationSnapshot).filter(
            ValuationSnapshot.investor_shares_id == holding.id,
            ValuationSnapshot.valuation_date >= trade_date,
        ).all()
        for snap in later:
            snap.shares_held = max(Decimal("0"), Decimal(str(snap.shares_held)) - take)
            snap.market_value = (Decimal(str(snap.shares_held)) * Decimal(str(snap.nav_per_share))).quantize(CENT)
        if not any(s.valuation_date == trade_date for s in later):
            dep_nav = Decimal(str(holding.deployment_nav or 0))
            session.add(ValuationSnapshot(
                investor_shares_id=holding.id,
                valuation_date=trade_date,
                nav_per_share=nav,
                shares_held=after,
                market_value=(after * nav).quantize(CENT),
                performance_pct=(((nav / dep_nav) - 1) * 100).quantize(Decimal("0.0001")) if dep_nav else Decimal("0"),
            ))

    session.commit()

    try:
        from app.Batch.controllers import BatchController
        if touched_batch_ids:
            BatchController.refresh_cached_total_capital_for_batch_ids(list(touched_batch_ids), session)
    except Exception:
        session.rollback()
    try:
        from app.Funds.routes import invalidate_funds_summary_cache
        invalidate_funds_summary_cache()
    except Exception:
        pass
    return withdrawal
