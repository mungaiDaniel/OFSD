"""
Manual per-investor Transfer amounts (FUNDS) — "list all clients, enter
amount received" feature.
=============================================================================
Replaces the pro-rata transaction-cost split with the real amount that
landed in the bank for each investor, still applying one batch-wide entry
fee % on top of each investor's real received amount. Legacy pro-rata mode
(no amounts_received) must keep working unchanged.

Run with: pytest tests/test_transfer_manual_amounts.py -v
"""

import json
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Batch.model import Batch
from app.Investments.model import Investment


def get_auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_funds_batch_with_investments(amounts):
    fund = CoreFund(fund_name="Axiom Transfer Test", fund_code="AXM-XFER")
    db.session.add(fund)
    db.session.flush()
    share_class = ShareClass(core_fund_id=fund.id, class_name="Axiom Class", class_code="AXM-XFER-I", currency="USD")
    db.session.add(share_class)
    db.session.flush()
    batch = Batch(batch_name="Axiom Transfer Batch", share_class_id=share_class.id, stage=1, is_active=True)
    db.session.add(batch)
    db.session.flush()

    investments = []
    for i, amount in enumerate(amounts, start=1):
        inv = Investment(
            investor_name=f"Investor {i}",
            investor_email=f"investor{i}@example.com",
            internal_client_code=f"XFER-{i}",
            amount_deposited=Decimal(str(amount)),
            batch_id=batch.id,
            fund_id=fund.id,
            share_class_id=share_class.id,
        )
        db.session.add(inv)
        investments.append(inv)
    db.session.commit()
    for inv in investments:
        db.session.refresh(inv)
    return batch, investments


@pytest.mark.unit
class TestManualTransferAmounts:
    def test_manual_amounts_use_real_received_value_per_investor(self, client, auth_token, app):
        with app.app_context():
            batch, investments = _make_funds_batch_with_investments(["2000.00", "3000.00"])
            inv_a, inv_b = investments

            # Investor A: full amount arrived. Investor B: bank only sent 2800
            # (200 lost to the bank's own cut) — entered directly, no formula.
            payload = {
                "is_transferred": True,
                "entry_fee_percentage": "2",
                "transfer_amounts_received": {
                    str(inv_a.id): "2000.00",
                    str(inv_b.id): "2800.00",
                },
            }
            resp = client.patch(
                f"/api/v1/batches/{batch.id}",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 200

            a = db.session.get(Investment, inv_a.id)
            b = db.session.get(Investment, inv_b.id)

            # A: received in full -> transfer_fee_deducted (implicit bank cut) = 0.
            assert a.transfer_amount_received == Decimal("2000.00")
            assert a.transfer_fee_deducted == Decimal("0.00")
            assert a.deployment_fee_deducted == Decimal("40.00")  # 2% of 2000

            # B: bank took 200 -> transfer_fee_deducted reflects that gap exactly.
            assert b.transfer_amount_received == Decimal("2800.00")
            assert b.transfer_fee_deducted == Decimal("200.00")
            assert b.deployment_fee_deducted == Decimal("60.00")  # 2% of the 3000 deposit, not the 2800 received
            assert b.net_principal == Decimal("2740.00")  # 3000 - 200 transfer - 60 entry fee

    def test_investor_missing_from_map_defaults_to_full_deposit(self, client, auth_token, app):
        with app.app_context():
            batch, investments = _make_funds_batch_with_investments(["1000.00", "1500.00"])
            inv_a, inv_b = investments

            payload = {
                "is_transferred": True,
                "entry_fee_percentage": "0",
                # Only inv_a is entered — inv_b is left out entirely.
                "transfer_amounts_received": {str(inv_a.id): "900.00"},
            }
            resp = client.patch(
                f"/api/v1/batches/{batch.id}",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 200

            b = db.session.get(Investment, inv_b.id)
            assert b.transfer_amount_received == Decimal("1500.00")
            assert b.transfer_fee_deducted == Decimal("0.00")

    def test_legacy_pro_rata_mode_unchanged_when_no_amounts_received(self, client, auth_token, app):
        with app.app_context():
            batch, investments = _make_funds_batch_with_investments(["2000.00", "6000.00"])
            inv_a, inv_b = investments

            payload = {
                "is_transferred": True,
                "transfer_transaction_cost": "80",
                "entry_fee_percentage": "0",
            }
            resp = client.patch(
                f"/api/v1/batches/{batch.id}",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 200

            a = db.session.get(Investment, inv_a.id)
            b = db.session.get(Investment, inv_b.id)
            # Pro-rata by deposit share: A=2000/8000*80=20.00, B=6000/8000*80=60.00
            assert a.transfer_fee_deducted == Decimal("20.00")
            assert b.transfer_fee_deducted == Decimal("60.00")
            # Legacy mode never touches the new column.
            assert a.transfer_amount_received is None
            assert b.transfer_amount_received is None

    def test_aggregate_mode_entry_fee_charged_on_initial_deposit(self, client, auth_token, app):
        with app.app_context():
            batch, investments = _make_funds_batch_with_investments(["2000.00", "6000.00"])
            inv_a, _ = investments

            payload = {
                "is_transferred": True,
                "transfer_transaction_cost": "80",
                "entry_fee_percentage": "2",
            }
            resp = client.patch(
                f"/api/v1/batches/{batch.id}",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 200

            a = db.session.get(Investment, inv_a.id)
            assert a.transfer_fee_deducted == Decimal("20.00")   # 2000/8000 * 80
            assert a.deployment_fee_deducted == Decimal("40.00")  # 2% of 2000 deposit (not of 1980)
            assert a.net_principal == Decimal("1940.00")
