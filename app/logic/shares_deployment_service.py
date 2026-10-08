"""
Deployment for SHARES (DPRP) batches: USD -> NGN conversion and share
allocation — Task 3, corrected by Task 7.

Replaces the old flat-rate DPRP oversubscription allocation
(BatchController.apply_oversubscription_allocation, now removed) with ONE
implementation that always runs the same conversion/allocation math, whether
or not the batch ends up oversubscribed. It reuses the existing
Withdrawals/Refunds pipeline (Withdrawal.source=oversubscription_refund,
status=Pending) exactly as that old code did, so maker-checker approval and
the investor-facing refund-notice email/PDF (EmailService.
send_oversubscription_refund_notices, app.Investments.route.
_get_oversubscription_refund_context) need no changes.

Task 7 correction: price_per_share_ngn is NOT an ongoing valuation — it is
used ONLY here, once, to convert each investor's net NGN into the whole
number of shares bought (Steps A-D below). After deployment, a SHARES
holding is valued exactly like a FUNDS holding: shares_owned x the latest
NAV-per-share (NGN) for this batch's share class, via the same InvestorShares
/ NavHistory mechanism FUNDS deployment already uses (see app/Batch/route.py
's FUNDS deployment confirm handler for the pattern this mirrors) — not a
fixed price fixed at deployment. apply_to_batch therefore also creates one
InvestorShares row per investment (deployment_nav=price_per_share_ngn, the
NGN cost basis) and sets Investment.previous_nav_price / opening_market_value
and Batch.deployment_nav, so the existing, product-agnostic NAV valuation
pipeline (POST /api/v1/valuation/nav, keyed purely by share_class_id) can
revalue this share class exactly as it does any FUNDS share class.

Algorithm (per deposit, all amounts in NGN unless stated otherwise):
    net_ngn_i      = net_usd_i * exchange_rate                         (Step A)
    max_shares_i   = floor(net_ngn_i / price_per_share_ngn)
    total_demand   = SUM(max_shares_i)

    shares_allocated >= total_demand (Step B): everyone gets max_shares_i.

    shares_allocated < total_demand (Step C), two rounds:
      tier1_shares_i = floor(MIN(net_ngn_i, net_ngn of a MIN_DEPOSIT_USD
                       deposit under this batch's own entry-fee/tx-cost %)
                       / price_per_share_ngn)
      Round 1: if SUM(tier1_shares_i) <= shares_allocated, everyone gets
               tier1_shares_i; else pro-rata floor(shares_allocated *
               tier1_shares_i / SUM(tier1_shares_i)) and Round 2 is skipped.
      Round 2 (only if shares remain): pro-rata the remainder over each
               investor's excess_i = max_shares_i - tier1_shares_i, never
               exceeding excess_i.

    refund_usd_i = (net_ngn_i - allocated_shares_i * price_per_share_ngn)
                   / exchange_rate                                      (Step D)

Rounding down at every step can leave a few shares unallocated — that
remainder is reported, never redistributed.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from datetime import datetime, timezone
from typing import List, Optional

from app.Investments.model import Investment
from app.logic.shares_transfer_service import get_min_deposit_usd

CENT = Decimal("0.01")


class SharesDeploymentError(ValueError):
    """Invalid input for a SHARES batch deployment allocation."""


def _round2(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _floor_shares(value: Decimal) -> int:
    return int(Decimal(value).to_integral_value(rounding=ROUND_FLOOR))


def _pre_refund_net_usd(inv: Investment) -> Decimal:
    """
    net_usd for deployment purposes — deliberately NOT Investment.net_principal,
    which already subtracts any EXISTING oversubscription_refund_amount. Reading
    the fee-deducted columns directly instead (same guard the old flat-rate
    allocation used) is what makes re-running this calculation idempotent
    rather than compounding a previous run's refund into the next one.
    """
    return (
        Decimal(str(inv.amount_deposited or 0))
        - Decimal(str(inv.transfer_fee_deducted or 0))
        - Decimal(str(inv.deployment_fee_deducted or 0))
    )


@dataclass
class ShareDeploymentRow:
    investment: Investment
    net_usd: Decimal
    net_ngn: Decimal
    max_shares: int
    tier1_shares: int = 0
    round2_shares: int = 0
    allocated_shares: int = 0
    refund_usd: Decimal = field(default_factory=lambda: Decimal("0.00"))

    def to_dict(self):
        return {
            "investment_id": self.investment.id,
            "internal_client_code": self.investment.internal_client_code,
            "net_usd": float(self.net_usd),
            "net_ngn": float(self.net_ngn),
            "max_shares": self.max_shares,
            "tier1_shares": self.tier1_shares,
            "round2_shares": self.round2_shares,
            "allocated_shares": self.allocated_shares,
            "refund_usd": float(self.refund_usd),
        }


class SharesDeploymentService:

    @staticmethod
    def _infer_batch_fee_ratios(investments: List[Investment]):
        """
        Derive the entry-fee % and proportional transaction-cost % actually
        applied to this batch at the Transferred stage (Task 2) from the
        persisted per-investment fields, computed from aggregate sums (not a
        single row) so any single row's rounding doesn't skew the ratio.
        """
        total_deposit = sum((Decimal(str(inv.amount_deposited or 0)) for inv in investments), Decimal("0"))
        total_entry_fee = sum((Decimal(str(inv.deployment_fee_deducted or 0)) for inv in investments), Decimal("0"))
        total_balance_after_entry = sum(
            (Decimal(str(inv.balance_after_entry_fee_usd or 0)) for inv in investments), Decimal("0")
        )
        total_tx_cost = sum((Decimal(str(inv.transfer_fee_deducted or 0)) for inv in investments), Decimal("0"))

        if total_deposit <= 0:
            raise SharesDeploymentError("Batch has no deposits to deploy")

        entry_fee_ratio = total_entry_fee / total_deposit
        tx_cost_ratio = (total_tx_cost / total_balance_after_entry) if total_balance_after_entry > 0 else Decimal("0")
        return entry_fee_ratio, tx_cost_ratio

    @classmethod
    def validate_inputs(cls, investments, exchange_rate, price_per_share_ngn, shares_allocated):
        if not investments:
            raise SharesDeploymentError("Batch has no deposits to deploy")

        try:
            exchange_rate = Decimal(str(exchange_rate))
        except Exception:
            raise SharesDeploymentError("exchange_rate must be a number")
        try:
            price_per_share_ngn = Decimal(str(price_per_share_ngn))
        except Exception:
            raise SharesDeploymentError("price_per_share_ngn must be a number")
        try:
            shares_allocated_dec = Decimal(str(shares_allocated))
        except Exception:
            raise SharesDeploymentError("shares_allocated must be a whole number")

        if exchange_rate <= 0:
            raise SharesDeploymentError("exchange_rate must be greater than 0")
        if price_per_share_ngn <= 0:
            raise SharesDeploymentError("price_per_share_ngn must be greater than 0")
        if shares_allocated_dec <= 0:
            raise SharesDeploymentError("shares_allocated must be greater than 0")
        if shares_allocated_dec != shares_allocated_dec.to_integral_value():
            raise SharesDeploymentError("shares_allocated must be a whole number")

        not_transferred = [
            inv.internal_client_code for inv in investments if inv.date_transferred is None
        ]
        if not_transferred:
            raise SharesDeploymentError(
                f"Deposit(s) have not been through the Transferred step yet: {', '.join(not_transferred)}"
            )

        return exchange_rate, price_per_share_ngn, int(shares_allocated_dec)

    @classmethod
    def calculate(cls, investments: List[Investment], exchange_rate, price_per_share_ngn, shares_allocated):
        """Pure calculation (no DB writes). Returns (rows, totals)."""
        exchange_rate, price_per_share_ngn, shares_allocated = cls.validate_inputs(
            investments, exchange_rate, price_per_share_ngn, shares_allocated
        )
        entry_fee_ratio, tx_cost_ratio = cls._infer_batch_fee_ratios(investments)
        min_deposit_usd = get_min_deposit_usd()
        min_deposit_net_usd = min_deposit_usd * (Decimal("1") - entry_fee_ratio) * (Decimal("1") - tx_cost_ratio)
        min_deposit_net_ngn = _round2(min_deposit_net_usd * exchange_rate)

        rows: List[ShareDeploymentRow] = []
        for inv in investments:
            net_usd = _pre_refund_net_usd(inv)
            net_ngn = _round2(net_usd * exchange_rate)
            rows.append(ShareDeploymentRow(
                investment=inv,
                net_usd=net_usd,
                net_ngn=net_ngn,
                max_shares=_floor_shares(net_ngn / price_per_share_ngn),
            ))

        total_demand = sum(r.max_shares for r in rows)
        is_oversubscribed = shares_allocated < total_demand

        if not is_oversubscribed:
            # Step B — everyone gets what they asked for.
            for r in rows:
                r.tier1_shares = r.max_shares
                r.allocated_shares = r.max_shares
        else:
            # Step C — tier-1 (minimum) amount first, capped at this batch's own
            # minimum-deposit net value so no one's tier-1 share exceeds what a
            # MIN_DEPOSIT_USD depositor would get.
            for r in rows:
                tier1_ngn = min(r.net_ngn, min_deposit_net_ngn)
                r.tier1_shares = _floor_shares(tier1_ngn / price_per_share_ngn)

            sum_tier1 = sum(r.tier1_shares for r in rows)

            if sum_tier1 == 0:
                # Not even a token allocation is affordable at this price — nothing
                # to allocate; everything reported as unallocated.
                pass
            elif sum_tier1 <= shares_allocated:
                for r in rows:
                    r.allocated_shares = r.tier1_shares
                remaining = shares_allocated - sum_tier1
                excess_by_row = {id(r): r.max_shares - r.tier1_shares for r in rows}
                sum_excess = sum(excess_by_row.values())
                if remaining > 0 and sum_excess > 0:
                    for r in rows:
                        excess = excess_by_row[id(r)]
                        if excess <= 0:
                            continue
                        proportional = _floor_shares(Decimal(remaining) * Decimal(excess) / Decimal(sum_excess))
                        r.round2_shares = min(excess, proportional)
                        r.allocated_shares += r.round2_shares
            else:
                # Round 1 cannot even be fully covered — pro-rata the minimums,
                # Round 2 is skipped entirely (no one gets more than tier-1).
                for r in rows:
                    r.allocated_shares = _floor_shares(
                        Decimal(shares_allocated) * Decimal(r.tier1_shares) / Decimal(sum_tier1)
                    )

        total_allocated = sum(r.allocated_shares for r in rows)
        unallocated_shares = shares_allocated - total_allocated

        # Step D — refund whatever NGN value didn't convert into a whole share,
        # for every row (true oversubscription or just floor-rounding leftover).
        for r in rows:
            allocated_ngn = Decimal(r.allocated_shares) * price_per_share_ngn
            unallocated_ngn = r.net_ngn - allocated_ngn
            r.refund_usd = _round2(unallocated_ngn / exchange_rate) if unallocated_ngn > 0 else Decimal("0.00")

        totals = {
            "net_usd": _round2(sum((r.net_usd for r in rows), Decimal("0"))),
            "net_ngn": _round2(sum((r.net_ngn for r in rows), Decimal("0"))),
            "total_demand_shares": total_demand,
            "shares_allocated": shares_allocated,
            "total_allocated_shares": total_allocated,
            "unallocated_shares": unallocated_shares,
            "total_refund_usd": _round2(sum((r.refund_usd for r in rows), Decimal("0"))),
            "is_oversubscribed": is_oversubscribed,
            "exchange_rate": exchange_rate,
            "price_per_share_ngn": price_per_share_ngn,
        }
        return rows, totals

    @classmethod
    def preview(cls, batch, session, exchange_rate, price_per_share_ngn, shares_allocated):
        """Dry-run for the deployment preview screen — no DB writes."""
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        rows, totals = cls.calculate(investments, exchange_rate, price_per_share_ngn, shares_allocated)
        return {
            "rows": [r.to_dict() for r in rows],
            "totals": {k: (float(v) if isinstance(v, Decimal) else v) for k, v in totals.items()},
            "banner": "Oversubscribed" if totals["is_oversubscribed"] else "Fully subscribed",
        }

    @classmethod
    def apply_to_batch(cls, batch, session, exchange_rate, price_per_share_ngn, shares_allocated):
        """
        Calculates and persists the deployment allocation onto every Investment
        in `batch`, in one transaction (a single commit at the end — nothing is
        written if calculate()/validate_inputs() raises). Creates or updates a
        Pending Withdrawal (source=oversubscription_refund) for every investor
        with a nonzero refund, reusing the exact same refund pipeline the old
        flat-rate allocation used.

        Deterministic/idempotent: calling this again with the same inputs before
        the batch is locked (deployment_confirmed) reproduces the same result —
        _pre_refund_net_usd ignores any refund already written by a prior run,
        and existing refund Withdrawals are updated in place rather than
        duplicated.
        """
        from app.Investments.model import (
            Withdrawal, WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND, WITHDRAWAL_STATUS_PENDING,
        )
        from app.Funds.investor_shares import InvestorShares

        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        rows, totals = cls.calculate(investments, exchange_rate, price_per_share_ngn, shares_allocated)

        existing_refunds_by_code = {
            w.internal_client_code: w
            for w in session.query(Withdrawal).filter(
                Withdrawal.batch_id == batch.id,
                Withdrawal.source == WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            ).all()
        }

        now = datetime.now(timezone.utc)
        note = (
            f"SHARES deployment refund — {batch.batch_name} "
            f"(rate {totals['exchange_rate'].normalize()}, price {totals['price_per_share_ngn'].normalize()} NGN/share)"
        )

        deployment_date = (batch.date_deployed.date() if batch.date_deployed else now.date())

        investment_mappings = []
        withdrawal_updates = []
        withdrawal_inserts = []
        refunded_investor_ids = []
        investor_shares_upserts = []

        existing_shares_by_investment_id = {
            s.investment_id: s
            for s in session.query(InvestorShares).filter(
                InvestorShares.investment_id.in_([r.investment.id for r in rows])
            ).all()
        }

        for r in rows:
            inv = r.investment
            # opening_market_value here is the NGN cost basis at deployment
            # (shares x price paid) — the FUNDS-equivalent field, read by
            # BatchController._calculate_batch_investment_values's fallback
            # tiers exactly as it is for a FUNDS deposit.
            opening_market_value_ngn = _round2(Decimal(r.allocated_shares) * totals["price_per_share_ngn"])
            investment_mappings.append({
                "id": inv.id,
                "shares_owned": Decimal(r.allocated_shares),
                "shares_exchange_rate_ngn": totals["exchange_rate"],
                "shares_price_per_share_ngn": totals["price_per_share_ngn"],
                "net_ngn": r.net_ngn,
                "oversubscription_refund_amount": r.refund_usd,
                "previous_nav_price": totals["price_per_share_ngn"],
                "opening_market_value": opening_market_value_ngn,
            })

            # Task 7: the InvestorShares row is what makes this holding
            # eligible for the same NAV-per-share revaluation pipeline FUNDS
            # uses (NavHistory.resolve_current_price, the committed NAV
            # valuation endpoint) — upserted so re-running deployment before
            # the batch locks stays idempotent, same as the fields above.
            existing_shares = existing_shares_by_investment_id.get(inv.id)
            investor_shares_upserts.append({
                **({"id": existing_shares.id} if existing_shares else {}),
                "investment_id": inv.id,
                "share_class_id": inv.share_class_id or batch.share_class_id,
                "batch_id": batch.id,
                "shares_owned": Decimal(r.allocated_shares),
                "deployment_nav": totals["price_per_share_ngn"],
                "deployment_date": deployment_date,
                "is_active": True,
            })

            if r.refund_usd > 0:
                refunded_investor_ids.append(inv.id)
                existing_refund = existing_refunds_by_code.get(inv.internal_client_code)
                if existing_refund:
                    withdrawal_updates.append({
                        "id": existing_refund.id,
                        "gross_amount": r.refund_usd,
                        "amount": r.refund_usd,
                        "note": note,
                        "status": WITHDRAWAL_STATUS_PENDING,
                    })
                else:
                    withdrawal_inserts.append({
                        "internal_client_code": inv.internal_client_code,
                        "fund_id": inv.fund_id,
                        "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                        "gross_amount": r.refund_usd,
                        "exit_fee_deducted": Decimal("0.00"),
                        "amount": r.refund_usd,
                        "date_withdrawn": now,
                        "status": WITHDRAWAL_STATUS_PENDING,
                        "note": note,
                        "batch_id": batch.id,
                        "source": WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                    })

        if investment_mappings:
            session.bulk_update_mappings(Investment, investment_mappings)
        if withdrawal_updates:
            session.bulk_update_mappings(Withdrawal, withdrawal_updates)
        if withdrawal_inserts:
            session.execute(Withdrawal.__table__.insert(), withdrawal_inserts)

        investor_shares_updates = [m for m in investor_shares_upserts if "id" in m]
        investor_shares_inserts = [m for m in investor_shares_upserts if "id" not in m]
        if investor_shares_updates:
            session.bulk_update_mappings(InvestorShares, investor_shares_updates)
        if investor_shares_inserts:
            session.execute(InvestorShares.__table__.insert(), investor_shares_inserts)

        batch.shares_exchange_rate_ngn = totals["exchange_rate"]
        batch.shares_price_per_share_ngn = totals["price_per_share_ngn"]
        # Task 7: the FUNDS-equivalent generic field, so deployment-NAV display
        # elsewhere (batch detail stat card, etc.) works for SHARES the same way.
        batch.deployment_nav = totals["price_per_share_ngn"]
        batch.shares_allocated_total = totals["shares_allocated"]
        batch.shares_demand_total = totals["total_demand_shares"]
        batch.shares_unallocated_total = totals["unallocated_shares"]
        batch.is_oversubscribed = totals["is_oversubscribed"]
        batch.total_shares = Decimal(totals["total_allocated_shares"])
        batch.deployment_total_nav = _round2(Decimal(totals["total_allocated_shares"]) * totals["price_per_share_ngn"])
        session.add(batch)

        session.commit()

        return {
            **{k: (float(v) if isinstance(v, Decimal) else v) for k, v in totals.items()},
            "_refunded_investor_ids": refunded_investor_ids,
        }

    @classmethod
    def revert_lock(cls, batch, session):
        """
        Admin "move batch back" action: clears the locked per-investment and
        batch-level deployment fields, and rejects any still-Pending refund
        Withdrawals created by the deployment being reverted (an approved/
        processed refund is left alone — it already paid out real money).
        Returns (old_values, new_values) for the caller to audit-log.
        """
        from app.Investments.model import Withdrawal, WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND
        from app.Funds.investor_shares import InvestorShares

        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        old_values = {
            "shares_exchange_rate_ngn": float(batch.shares_exchange_rate_ngn or 0),
            "shares_price_per_share_ngn": float(batch.shares_price_per_share_ngn or 0),
            "shares_allocated_total": batch.shares_allocated_total,
            "shares_demand_total": batch.shares_demand_total,
            "shares_unallocated_total": batch.shares_unallocated_total,
            "is_oversubscribed": batch.is_oversubscribed,
            "total_shares": float(batch.total_shares or 0),
            "rows": [
                {
                    "investment_id": inv.id,
                    "internal_client_code": inv.internal_client_code,
                    "shares_owned": float(inv.shares_owned or 0),
                    "net_ngn": float(inv.net_ngn or 0),
                    "refund_usd": float(inv.oversubscription_refund_amount or 0),
                }
                for inv in investments
            ],
        }

        mappings = [
            {
                "id": inv.id,
                "shares_owned": None,
                "shares_exchange_rate_ngn": None,
                "shares_price_per_share_ngn": None,
                "net_ngn": None,
                "oversubscription_refund_amount": Decimal("0.00"),
                "previous_nav_price": None,
                "opening_market_value": None,
            }
            for inv in investments
        ]
        if mappings:
            session.bulk_update_mappings(Investment, mappings)

        # This batch's own InvestorShares rows only (never another batch's,
        # even on the same share class) — any NavHistory/ValuationSnapshot
        # rows from a real committed valuation are left untouched, same as an
        # already-processed refund Withdrawal is left alone below: a
        # committed valuation already happened and reverting deployment
        # doesn't unmake it.
        session.query(InvestorShares).filter(InvestorShares.batch_id == batch.id).delete(synchronize_session=False)

        pending_refunds = session.query(Withdrawal).filter(
            Withdrawal.batch_id == batch.id,
            Withdrawal.source == WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            Withdrawal.status == "Pending",
        ).all()
        for refund in pending_refunds:
            refund.status = "Rejected"
            refund.note = f"{refund.note or ''} — auto-rejected: deployment reverted by admin".strip(" —")
            session.add(refund)

        batch.shares_exchange_rate_ngn = None
        batch.shares_price_per_share_ngn = None
        batch.deployment_nav = None
        batch.shares_allocated_total = None
        batch.shares_demand_total = None
        batch.shares_unallocated_total = None
        batch.is_oversubscribed = False
        batch.total_shares = None
        batch.deployment_total_nav = None
        session.add(batch)

        session.commit()

        new_values = {
            "shares_exchange_rate_ngn": None,
            "shares_price_per_share_ngn": None,
            "shares_allocated_total": None,
            "shares_demand_total": None,
            "shares_unallocated_total": None,
            "is_oversubscribed": False,
            "total_shares": None,
            "rows": [],
        }
        return old_values, new_values
