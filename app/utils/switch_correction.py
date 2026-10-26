"""
Correct a holding that was recorded in the wrong class share count after a
class switch (e.g. a Class R purchase that was switched to Class I).

Example: Esther Makara (1966812) bought into Class R (2,270.27 shares at 1,295.00)
and was switched to Class I on 10 Aug 2026 (2,187.58 shares at 1,418.5235). The
system kept the Class R share count as Class I.

What changes (for ONE deployed holding, in ONE transaction):
  - the holding's shares, deployment NAV and deployment date
  - the matching Investment fields (shares_owned, previous_nav_price,
    opening_market_value, date_transferred)
  - the batch's deployment date / NAV / total shares / total NAV (single-holding batches only)
  - that holding's own valuation snapshots: shares_held, market_value and
    performance_pct are recomputed from the corrected shares and deployment NAV
  - the batch's cached total capital

What does NOT change: the amount deposited and fees (the cost stays as paid),
every other holding, other batches, valuation NAVs, NAV history, withdrawals.

Dry run by default: nothing is saved unless apply=True.
"""

from datetime import datetime, timezone, date as date_type
from decimal import Decimal

from sqlalchemy import func, insert

from app.Batch.model import Batch
from app.Funds.investor_shares import InvestorShares
from app.Investments.model import Investment
from app.Valuation.valuation_snapshot import ValuationSnapshot

CENT = Decimal("0.01")


class SwitchCorrectionError(ValueError):
    """The requested correction is unsafe or inconsistent; nothing was changed."""


def _d(x):
    return Decimal(str(x))


def apply_switch_correction(
    session,
    batch_id: int,
    shares,
    nav,
    switch_date: date_type,
    investment_id: int | None = None,
    expected_value=None,
    apply: bool = False,
    actor: str = "script",
):
    shares, nav = _d(shares), _d(nav)
    if shares <= 0 or nav <= 0:
        raise SwitchCorrectionError("shares and nav must be positive")
    if switch_date > datetime.now(timezone.utc).date():
        raise SwitchCorrectionError("switch date cannot be in the future")

    batch = session.query(Batch).filter(Batch.id == batch_id).first()
    if batch is None:
        raise SwitchCorrectionError(f"Batch {batch_id} not found")
    if not batch.deployment_confirmed:
        raise SwitchCorrectionError("Batch has not been deployed")

    investments = session.query(Investment).filter(Investment.batch_id == batch_id).all()
    if investment_id is None:
        if len(investments) != 1:
            raise SwitchCorrectionError(
                f"Batch has {len(investments)} investments; pass investment_id to choose one"
            )
        inv = investments[0]
    else:
        inv = next((i for i in investments if i.id == investment_id), None)
        if inv is None:
            raise SwitchCorrectionError(f"Investment {investment_id} is not in batch {batch_id}")
    if len(investments) != 1:
        raise SwitchCorrectionError(
            "Only single-investment batches are supported: the batch deployment figures would "
            "otherwise be wrong for the other clients."
        )

    holding = session.query(InvestorShares).filter(InvestorShares.investment_id == inv.id).first()
    if holding is None:
        raise SwitchCorrectionError("Investment has no share holding")

    if switch_date < (inv.date_deposited.date() if inv.date_deposited else switch_date):
        raise SwitchCorrectionError("switch date cannot be before the deposit date")

    value = (shares * nav).quantize(CENT)
    if expected_value is not None and abs(value - _d(expected_value)) > Decimal("1.00"):
        raise SwitchCorrectionError(
            f"shares x NAV = {value} but expected value is {_d(expected_value)}; check the inputs"
        )

    snapshots = (
        session.query(ValuationSnapshot)
        .filter(ValuationSnapshot.investor_shares_id == holding.id)
        .order_by(ValuationSnapshot.valuation_date.asc())
        .all()
    )
    early = [s.valuation_date.isoformat() for s in snapshots if s.valuation_date < switch_date]
    if early:
        raise SwitchCorrectionError(
            f"Valuations exist before the switch date ({', '.join(early)}); resolve those first"
        )

    before = {
        "investment": {
            "shares_owned": str(inv.shares_owned),
            "previous_nav_price": str(inv.previous_nav_price),
            "opening_market_value": str(inv.opening_market_value),
            "date_transferred": inv.date_transferred.isoformat() if inv.date_transferred else None,
            "amount_deposited": str(inv.amount_deposited),
        },
        "holding": {
            "shares_owned": str(holding.shares_owned),
            "deployment_nav": str(holding.deployment_nav),
            "deployment_date": holding.deployment_date.isoformat(),
        },
        "batch": {
            "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
            "deployment_date_actual": batch.deployment_date_actual.isoformat() if batch.deployment_date_actual else None,
            "deployment_nav": str(batch.deployment_nav),
            "total_shares": str(batch.total_shares),
            "deployment_total_nav": str(batch.deployment_total_nav),
        },
        "snapshots": [
            {"date": s.valuation_date.isoformat(), "shares_held": str(s.shares_held), "nav": str(s.nav_per_share),
             "market_value": str(s.market_value), "performance_pct": str(s.performance_pct)}
            for s in snapshots
        ],
    }

    when = datetime.combine(switch_date, datetime.min.time(), tzinfo=timezone.utc)

    inv.shares_owned = shares
    inv.previous_nav_price = nav
    inv.opening_market_value = value
    inv.date_transferred = when
    session.add(inv)

    holding.shares_owned = shares
    holding.deployment_nav = nav
    holding.deployment_date = switch_date
    session.add(holding)

    batch.deployment_nav = nav
    batch.total_shares = shares
    batch.deployment_total_nav = value
    batch.deployment_date_actual = switch_date
    batch.date_deployed = when
    session.add(batch)

    for s in snapshots:
        snap_nav = _d(s.nav_per_share)
        s.shares_held = shares
        s.market_value = (shares * snap_nav).quantize(CENT)
        s.performance_pct = ((snap_nav / nav - 1) * 100).quantize(Decimal("0.0001"))
        session.add(s)

    session.flush()

    after = {
        "investment": {"shares_owned": str(shares), "previous_nav_price": str(nav), "opening_market_value": str(value),
                       "date_transferred": when.isoformat(), "amount_deposited": str(inv.amount_deposited)},
        "holding": {"shares_owned": str(shares), "deployment_nav": str(nav), "deployment_date": switch_date.isoformat()},
        "batch": {"date_deployed": when.isoformat(), "deployment_date_actual": switch_date.isoformat(),
                  "deployment_nav": str(nav), "total_shares": str(shares), "deployment_total_nav": str(value)},
        "snapshots": [
            {"date": s.valuation_date.isoformat(), "shares_held": str(s.shares_held), "nav": str(s.nav_per_share),
             "market_value": str(s.market_value), "performance_pct": str(s.performance_pct)}
            for s in snapshots
        ],
    }

    class_shares_after = session.query(func.coalesce(func.sum(InvestorShares.shares_owned), 0)).filter(
        InvestorShares.share_class_id == holding.share_class_id, InvestorShares.is_active == True
    ).scalar()
    result = {
        "applied": bool(apply),
        "investment_id": inv.id,
        "client_code": inv.internal_client_code,
        "before": before,
        "after": after,
        "class_total_shares_after": str(class_shares_after),
    }

    if apply:
        import json
        from app.utils.audit_log import AuditLog
        session.execute(insert(AuditLog), [{
            "user_email": actor, "user_name": actor,
            "action": "SWITCH_CORRECTION", "target_type": "investment", "target_id": inv.id,
            "target_name": inv.internal_client_code,
            "description": f"Corrected class-switch holding for {inv.internal_client_code} in batch {batch_id}: "
                           f"{before['holding']['shares_owned']} -> {shares} shares, NAV {nav}, date {switch_date}",
            "new_value": json.dumps({"before": before, "after": after}, default=str),
            "ip_address": None, "user_agent": "switch_correction", "timestamp": datetime.now(timezone.utc), "success": True,
        }])
        session.commit()
        # Refresh the cached batch total AFTER the real commit (this helper commits
        # on its own, so it must never run inside a dry run).
        try:
            from app.Batch.controllers import BatchController
            BatchController.refresh_cached_total_capital_for_batch_ids({batch.id}, session)
        except Exception:
            pass
    else:
        session.rollback()
    return result
