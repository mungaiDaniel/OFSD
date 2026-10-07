"""
SHARES (DPRP) Transfer-Stage Fee Tests — Task 2
=================================================
New entry-fee-first, proportional-transaction-cost calculation for SHARES
batches at the Transferred stage. FUNDS batches must keep today's behaviour.

Run with: pytest tests/test_shares_transfer_fees.py -v
"""

import json
from decimal import Decimal

import pytest

from app.database.database import db
from app.database.product_type import FUNDS, SHARES
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment
from app.logic.batch_management_service import BatchManagementService
from app.logic.shares_transfer_service import SharesTransferService, SharesTransferError
from app.utils.audit_log import AuditLog


def get_auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


def _make_fund_and_class(fund_name, fund_code, class_code="DPRP", currency="USD"):
    fund = CoreFund(fund_name=fund_name, fund_code=fund_code)
    db.session.add(fund)
    db.session.flush()
    share_class = ShareClass(
        core_fund_id=fund.id,
        class_name=f"{fund_name} Class",
        class_code=class_code,
        currency=currency,
    )
    db.session.add(share_class)
    db.session.flush()
    return fund, share_class


def _dprp_batch():
    _, share_class = _make_fund_and_class(
        "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
    )
    return BatchManagementService.find_or_create_batch(share_class.id)


def _axiom_batch():
    _, share_class = _make_fund_and_class("Axiom", "AXIOM", class_code="CI-USD")
    return BatchManagementService.find_or_create_batch(share_class.id)


def _investment(batch, code, amount, name=None):
    inv = Investment(
        batch_id=batch.id,
        investor_name=name or code,
        investor_email=f"{code.lower()}@example.com",
        internal_client_code=code,
        amount_deposited=Decimal(amount),
        share_class_id=batch.share_class_id,
    )
    db.session.add(inv)
    db.session.commit()
    return inv


class TestSharesTransferCalculation:
    """Pure calculation tests (no DB/HTTP) against the worked example in the task."""

    def test_worked_example_from_task(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")
                b = _investment(batch, "B", "2000.00")
                c = _investment(batch, "C", "6000.00")

                rows, totals = SharesTransferService.calculate([a, b, c], "2", "98")
                by_code = {r.investment.internal_client_code: r for r in rows}

                assert by_code["A"].entry_fee_usd == Decimal("40.00")
                assert by_code["B"].entry_fee_usd == Decimal("40.00")
                assert by_code["C"].entry_fee_usd == Decimal("120.00")

                assert by_code["A"].balance_after_entry == Decimal("1960.00")
                assert by_code["B"].balance_after_entry == Decimal("1960.00")
                assert by_code["C"].balance_after_entry == Decimal("5880.00")
                assert totals["balance_after_entry"] == Decimal("9800.00")

                assert by_code["A"].transaction_cost_usd == Decimal("19.60")
                assert by_code["B"].transaction_cost_usd == Decimal("19.60")
                assert by_code["C"].transaction_cost_usd == Decimal("58.80")
                assert totals["transaction_cost_usd"] == Decimal("98.00")

                assert by_code["A"].net_usd == Decimal("1940.40")
                assert by_code["B"].net_usd == Decimal("1940.40")
                assert by_code["C"].net_usd == Decimal("5821.20")
                assert totals["net_usd"] == Decimal("9702.00")
            finally:
                db.session.remove()
                db.drop_all()

    def test_rounding_residual_goes_to_largest_balance_and_sum_is_exact(self, app):
        """A split that doesn't divide evenly must still sum to the exact total."""
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                # Three equal deposits -> transaction cost splits into repeating
                # decimals; naive per-row rounding would make the sum off by a cent.
                a = _investment(batch, "A", "3000.00")
                b = _investment(batch, "B", "3000.00")
                c = _investment(batch, "C", "3000.00")

                rows, totals = SharesTransferService.calculate([a, b, c], "0", "100")
                tx_costs = [r.transaction_cost_usd for r in rows]

                assert sum(tx_costs, Decimal("0")) == Decimal("100.00")
                assert totals["transaction_cost_usd"] == Decimal("100.00")
                # Residual landed on exactly one row (equal balances -> the first
                # max() match, i.e. "A"), the other two share the even split.
                assert tx_costs.count(Decimal("33.33")) == 2
                assert Decimal("33.34") in tx_costs

                assert sum((r.net_usd for r in rows), Decimal("0")) == totals["net_usd"]
            finally:
                db.session.remove()
                db.drop_all()

    def test_entry_fee_percent_out_of_range_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([a], "150", "0")
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([a], "-1", "0")
            finally:
                db.session.remove()
                db.drop_all()

    def test_negative_total_transaction_cost_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([a], "2", "-10")
            finally:
                db.session.remove()
                db.drop_all()

    def test_total_transaction_cost_exceeding_balances_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")  # balance after 2% entry fee = 1960
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([a], "2", "1960")  # must be strictly less
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([a], "2", "5000")
            finally:
                db.session.remove()
                db.drop_all()

    def test_deposit_below_minimum_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "1999.99")
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([a], "2", "0")
            finally:
                db.session.remove()
                db.drop_all()

    def test_no_deposits_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                with pytest.raises(SharesTransferError):
                    SharesTransferService.calculate([], "2", "0")
            finally:
                db.session.remove()
                db.drop_all()


class TestMinimumDepositAtAddTime:
    """MIN_DEPOSIT_USD is enforced when a deposit is added to a SHARES batch, not just at transfer."""

    def test_below_minimum_rejected_on_add(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                investment = Investment(
                    investor_name="Too Small",
                    investor_email="small@example.com",
                    internal_client_code="SMALL-1",
                    amount_deposited=Decimal("500.00"),
                    share_class_id=batch.share_class_id,
                )
                with pytest.raises(ValueError):
                    BatchManagementService.add_investor_to_batch(investment, batch)
            finally:
                db.session.remove()
                db.drop_all()

    def test_at_or_above_minimum_accepted_on_add(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                investment = Investment(
                    investor_name="Exactly Min",
                    investor_email="min@example.com",
                    internal_client_code="MIN-1",
                    amount_deposited=Decimal("2000.00"),
                    share_class_id=batch.share_class_id,
                )
                result = BatchManagementService.add_investor_to_batch(investment, batch)
                assert result.id is not None

                funds_batch = _axiom_batch()
                small_funds_investment = Investment(
                    investor_name="Small Funds Deposit",
                    investor_email="smallfunds@example.com",
                    internal_client_code="SMALLFUNDS-1",
                    amount_deposited=Decimal("50.00"),
                    share_class_id=funds_batch.share_class_id,
                )
                # The minimum only applies to SHARES — FUNDS deposits are unaffected.
                result2 = BatchManagementService.add_investor_to_batch(small_funds_investment, funds_batch)
                assert result2.id is not None
            finally:
                db.session.remove()
                db.drop_all()


class TestSharesTransferApi:
    """End-to-end through PATCH /api/v1/batches/<id> and the preview endpoint."""

    def test_preview_endpoint_matches_worked_example(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                _investment(batch, "A", "2000.00")
                _investment(batch, "B", "2000.00")
                _investment(batch, "C", "6000.00")

                resp = client.get(
                    f'/api/v1/batches/{batch.id}/shares-transfer-preview'
                    f'?entry_fee_percent=2&total_transaction_cost_usd=98',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 200
                data = resp.get_json()["data"]
                assert data["totals"]["transaction_cost_usd"] == pytest.approx(98.00)
                assert data["totals"]["net_usd"] == pytest.approx(9702.00)
                assert len(data["rows"]) == 3

                # Dry run — nothing persisted.
                db.session.expire_all()
                assert Batch.query.get(batch.id).is_transferred is False
            finally:
                db.session.remove()
                db.drop_all()

    def test_preview_rejected_for_funds_batch(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _axiom_batch()
                _investment(batch, "A", "2000.00")
                resp = client.get(
                    f'/api/v1/batches/{batch.id}/shares-transfer-preview'
                    f'?entry_fee_percent=2&total_transaction_cost_usd=10',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 400
            finally:
                db.session.remove()
                db.drop_all()

    def test_patch_transfer_applies_shares_fees_and_locks(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")
                b = _investment(batch, "B", "2000.00")
                c = _investment(batch, "C", "6000.00")

                payload = {
                    "is_transferred": True,
                    "entry_fee_percentage": 2,
                    "transfer_transaction_cost": 98,
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 200

                db.session.expire_all()
                batch = Batch.query.get(batch.id)
                assert batch.is_transferred is True
                assert batch.transfer_transaction_cost == Decimal("98.00")

                a, b, c = (db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id))
                assert a.deployment_fee_deducted == Decimal("40.00")  # entry fee
                assert a.balance_after_entry_fee_usd == Decimal("1960.00")
                assert a.transfer_fee_deducted == Decimal("19.60")  # transaction cost
                assert a.net_principal == Decimal("1940.40")
                assert c.net_principal == Decimal("5821.20")

                # Re-PATCHing transfer settings on an already-Transferred SHARES batch
                # must NOT change the locked fees.
                resp2 = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps({"entry_fee_percentage": 5, "transfer_transaction_cost": 500}),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp2.status_code == 200
                db.session.expire_all()
                a = db.session.get(Investment, a.id)
                assert a.deployment_fee_deducted == Decimal("40.00")  # unchanged — locked
            finally:
                db.session.remove()
                db.drop_all()

    def test_patch_transfer_rejects_invalid_inputs_without_mutating(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                _investment(batch, "A", "2000.00")

                payload = {
                    "is_transferred": True,
                    "entry_fee_percentage": 2,
                    "transfer_transaction_cost": 999999,  # far more than the balance
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 400

                db.session.expire_all()
                batch = Batch.query.get(batch.id)
                assert batch.is_transferred is False  # untouched
            finally:
                db.session.remove()
                db.drop_all()

    def test_funds_batch_transfer_unaffected_by_shares_changes(self, client, auth_token, app):
        """FUNDS batches keep their existing transfer-stage behaviour exactly."""
        with app.app_context():
            db.create_all()
            try:
                batch = _axiom_batch()
                a = _investment(batch, "A", "1000.00")
                b = _investment(batch, "B", "3000.00")

                payload = {
                    "is_transferred": True,
                    "entry_fee_percentage": 2,
                    "transfer_transaction_cost": 40,
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 200

                db.session.expire_all()
                a = db.session.get(Investment, a.id)
                # FUNDS order: transaction cost first (proportional to raw deposit),
                # THEN entry fee on what's left — the OPPOSITE of SHARES.
                # a: tx cost = 1000/4000*40 = 10.00; net_after_tx = 990.00; entry fee = 990*2% = 19.80
                assert a.transfer_fee_deducted == Decimal("10.00")
                assert a.deployment_fee_deducted == Decimal("19.80")
                assert a.balance_after_entry_fee_usd is None  # FUNDS never populates this
            finally:
                db.session.remove()
                db.drop_all()

    def test_revert_lock_unlocks_and_audits(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")
                b = _investment(batch, "B", "2000.00")

                transfer_payload = {
                    "is_transferred": True,
                    "entry_fee_percentage": 2,
                    "transfer_transaction_cost": 50,
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(transfer_payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 200

                revert_resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps({"is_transferred": False}),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert revert_resp.status_code == 200

                db.session.expire_all()
                batch = Batch.query.get(batch.id)
                assert batch.is_transferred is False
                assert batch.transfer_transaction_cost == Decimal("0.00")

                a = db.session.get(Investment, a.id)
                assert a.deployment_fee_deducted == Decimal("0.00")
                assert a.transfer_fee_deducted == Decimal("0.00")
                assert a.balance_after_entry_fee_usd is None

                audit_entry = AuditLog.query.filter_by(action="SHARES_TRANSFER_REVERTED", target_id=batch.id).first()
                assert audit_entry is not None
                assert audit_entry.old_value is not None  # old per-investment fee values captured

                # Transferring again recalculates from scratch.
                resp3 = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps({
                        "is_transferred": True,
                        "entry_fee_percentage": 2,
                        "transfer_transaction_cost": 10,
                    }),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp3.status_code == 200
                db.session.expire_all()
                a = db.session.get(Investment, a.id)
                assert a.deployment_fee_deducted == Decimal("40.00")
            finally:
                db.session.remove()
                db.drop_all()
