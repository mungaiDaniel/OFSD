"""
Transferred-stage fee calculation for SHARES (DPRP) batches — Task 2.

FUNDS batches keep their existing transfer-stage logic untouched (see
StatusUpdateController._apply_transfer_cost_deduction): transaction cost is
deducted first (proportional to the raw deposit), then the entry fee is taken
from what's left.

SHARES batches use the OPPOSITE order, per deposit, all in USD:
    1. entry_fee_usd        = deposit_usd * entry_fee_percent / 100
    2. balance_after_entry  = deposit_usd - entry_fee_usd
    3. transaction_cost_usd = total_transaction_cost_usd * balance_after_entry
                               / SUM(balance_after_entry over the batch)
    4. net_usd               = balance_after_entry - transaction_cost_usd

The transaction cost is always deducted from the balance AFTER the entry fee,
never from the original deposit.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from flask import current_app

from app.Investments.model import Investment

CENT = Decimal("0.01")


class SharesTransferError(ValueError):
    """Invalid input for a SHARES batch transfer-fee calculation."""


def _round2(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def get_min_deposit_usd() -> Decimal:
    """MIN_DEPOSIT_USD config value (defaults to 2000 if unset/unparseable)."""
    try:
        raw = current_app.config.get("MIN_DEPOSIT_USD", "2000")
    except RuntimeError:
        # No app context (e.g. a script); fall back to the documented default.
        raw = "2000"
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("2000")


@dataclass
class ShareTransferRow:
    investment: Investment
    deposit_usd: Decimal
    entry_fee_usd: Decimal
    balance_after_entry: Decimal
    transaction_cost_usd: Decimal
    net_usd: Decimal

    def to_dict(self):
        return {
            "investment_id": self.investment.id,
            "internal_client_code": self.investment.internal_client_code,
            "deposit_usd": float(self.deposit_usd),
            "entry_fee_usd": float(self.entry_fee_usd),
            "balance_after_entry": float(self.balance_after_entry),
            "transaction_cost_usd": float(self.transaction_cost_usd),
            "net_usd": float(self.net_usd),
        }


class SharesTransferService:
    """Transferred-stage fee calculation + persistence for SHARES batches."""

    @staticmethod
    def get_min_deposit_usd() -> Decimal:
        return get_min_deposit_usd()

    @classmethod
    def validate_inputs(
        cls,
        investments: List[Investment],
        entry_fee_percent,
        total_transaction_cost_usd,
    ) -> tuple:
        """Raises SharesTransferError with a clear message on any invalid input."""
        try:
            entry_fee_percent = Decimal(str(entry_fee_percent))
        except Exception:
            raise SharesTransferError("entry_fee_percent must be a number")
        try:
            total_transaction_cost_usd = Decimal(str(total_transaction_cost_usd))
        except Exception:
            raise SharesTransferError("total_transaction_cost_usd must be a number")

        if entry_fee_percent < 0 or entry_fee_percent > 100:
            raise SharesTransferError("entry_fee_percent must be between 0 and 100")
        if total_transaction_cost_usd < 0:
            raise SharesTransferError("total_transaction_cost_usd must be >= 0")
        if not investments:
            raise SharesTransferError("Batch has no deposits to transfer")

        min_deposit = cls.get_min_deposit_usd()
        below_min = [
            inv.internal_client_code
            for inv in investments
            if Decimal(str(inv.amount_deposited or 0)) < min_deposit
        ]
        if below_min:
            raise SharesTransferError(
                f"Deposit(s) below the {min_deposit} USD minimum (before fees): "
                f"{', '.join(below_min)}"
            )

        entry_fee_ratio = entry_fee_percent / Decimal("100")
        sum_balance_after_entry = sum(
            (Decimal(str(inv.amount_deposited)) * (Decimal("1") - entry_fee_ratio) for inv in investments),
            Decimal("0"),
        )
        if total_transaction_cost_usd >= sum_balance_after_entry:
            raise SharesTransferError(
                "total_transaction_cost_usd must be less than the sum of balances "
                "after the entry fee"
            )

        return entry_fee_percent, total_transaction_cost_usd

    @classmethod
    def calculate(
        cls,
        investments: List[Investment],
        entry_fee_percent,
        total_transaction_cost_usd,
    ):
        """
        Pure calculation (no DB writes). Returns (rows, totals) where rows is a
        list of ShareTransferRow (one per investment, same order as given) and
        totals is a dict of the same fields summed.
        """
        entry_fee_percent, total_transaction_cost_usd = cls.validate_inputs(
            investments, entry_fee_percent, total_transaction_cost_usd
        )
        entry_fee_ratio = entry_fee_percent / Decimal("100")

        deposits = [Decimal(str(inv.amount_deposited)) for inv in investments]
        entry_fees = [_round2(d * entry_fee_ratio) for d in deposits]
        balances_after_entry = [d - f for d, f in zip(deposits, entry_fees)]
        sum_balance_after_entry = sum(balances_after_entry, Decimal("0"))

        # Proportional split of the transaction cost over balance_after_entry,
        # rounded half-up per row; the residual cent (from rounding every row
        # independently) goes on the deposit with the largest balance so the
        # rows sum to total_transaction_cost_usd EXACTLY.
        tx_costs = []
        allocated = Decimal("0.00")
        for balance in balances_after_entry:
            share = _round2(total_transaction_cost_usd * balance / sum_balance_after_entry)
            tx_costs.append(share)
            allocated += share

        residual = total_transaction_cost_usd - allocated
        if residual != 0 and balances_after_entry:
            largest_idx = max(range(len(balances_after_entry)), key=lambda i: balances_after_entry[i])
            tx_costs[largest_idx] = _round2(tx_costs[largest_idx] + residual)

        rows = []
        for inv, deposit, entry_fee, balance, tx_cost in zip(
            investments, deposits, entry_fees, balances_after_entry, tx_costs
        ):
            net_usd = _round2(balance - tx_cost)
            rows.append(ShareTransferRow(
                investment=inv,
                deposit_usd=deposit,
                entry_fee_usd=entry_fee,
                balance_after_entry=_round2(balance),
                transaction_cost_usd=tx_cost,
                net_usd=net_usd,
            ))

        totals = {
            "deposit_usd": _round2(sum(deposits, Decimal("0"))),
            "entry_fee_usd": _round2(sum(entry_fees, Decimal("0"))),
            "balance_after_entry": _round2(sum_balance_after_entry),
            "transaction_cost_usd": _round2(sum(tx_costs, Decimal("0"))),
            "net_usd": _round2(sum((r.net_usd for r in rows), Decimal("0"))),
        }
        return rows, totals

    @classmethod
    def preview(cls, batch, session, entry_fee_percent, total_transaction_cost_usd):
        """Dry-run for the batch UI's fee-preview table — no DB writes."""
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        rows, totals = cls.calculate(investments, entry_fee_percent, total_transaction_cost_usd)
        return {
            "rows": [r.to_dict() for r in rows],
            "totals": {k: float(v) for k, v in totals.items()},
        }

    @classmethod
    def apply_to_batch(cls, batch, session, entry_fee_percent, total_transaction_cost_usd):
        """
        Calculates and persists the transfer fees onto every Investment in
        `batch`, storing entry_fee_usd in deployment_fee_deducted and
        transaction_cost_usd in transfer_fee_deducted — the same two columns
        FUNDS already (mis)names this way at the transfer stage, so
        Investment.net_principal (deposit - transfer_fee_deducted -
        deployment_fee_deducted - oversubscription_refund_amount) is net_usd
        for SHARES too, with no change needed to that property.

        Locking ("once Transferred, fees are locked") is enforced by the
        caller only invoking this once, when is_transferred is flipping
        False -> True (mirrors how the FUNDS path already only applies its
        deduction on that same transition) — see BatchController.patch_batch
        and StatusUpdateController.handle_status_transition.
        """
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        rows, totals = cls.calculate(investments, entry_fee_percent, total_transaction_cost_usd)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        mappings = [
            {
                "id": row.investment.id,
                "deployment_fee_deducted": row.entry_fee_usd,
                "balance_after_entry_fee_usd": row.balance_after_entry,
                "transfer_fee_deducted": row.transaction_cost_usd,
                "date_transferred": now,
            }
            for row in rows
        ]
        session.bulk_update_mappings(Investment, mappings)

        batch.transfer_transaction_cost = totals["transaction_cost_usd"]
        batch.is_transferred = True
        session.add(batch)
        session.commit()

        return totals

    @classmethod
    def revert_lock(cls, batch, session):
        """
        Admin "move batch back" action: clears the locked per-investment fee
        fields so the next Transferred run recalculates from scratch. Returns
        (old_totals, new_totals) for the caller to audit-log — old/new values,
        who and when are filled in by create_audit_log itself.
        """
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        old_totals = {
            "transfer_transaction_cost": float(batch.transfer_transaction_cost or 0),
            "rows": [
                {
                    "investment_id": inv.id,
                    "internal_client_code": inv.internal_client_code,
                    "entry_fee_usd": float(inv.deployment_fee_deducted or 0),
                    "balance_after_entry_fee_usd": float(inv.balance_after_entry_fee_usd or 0),
                    "transaction_cost_usd": float(inv.transfer_fee_deducted or 0),
                }
                for inv in investments
            ],
        }

        mappings = [
            {
                "id": inv.id,
                "deployment_fee_deducted": Decimal("0.00"),
                "balance_after_entry_fee_usd": None,
                "transfer_fee_deducted": Decimal("0.00"),
                "date_transferred": None,
            }
            for inv in investments
        ]
        if mappings:
            session.bulk_update_mappings(Investment, mappings)

        batch.transfer_transaction_cost = Decimal("0.00")
        session.add(batch)
        session.commit()

        new_totals = {"transfer_transaction_cost": 0.0, "rows": []}
        return old_totals, new_totals
