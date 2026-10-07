"""
SHARES (DPRP) Deployment Tests — Task 3
=========================================
USD -> NGN conversion and whole-share allocation at the Deployed transition.
Covers the worked examples in the task (fully subscribed, oversubscribed with
both rounds, and oversubscribed below the minimums), rounding-down behaviour,
an investor below MIN_DEPOSIT_USD, invalid inputs, and idempotency.

Run with: pytest tests/test_shares_deployment.py -v
"""

import json
from decimal import Decimal

import pytest

from app.database.database import db
from app.database.product_type import FUNDS, SHARES
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment, Withdrawal, WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND
from app.logic.batch_management_service import BatchManagementService
from app.logic.shares_transfer_service import SharesTransferService
from app.logic.shares_deployment_service import SharesDeploymentService, SharesDeploymentError
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


def _worked_example_batch():
    """A=2000, B=2000, C=6000 USD; entry 2%, tx cost 98 -> net_usd 1940.40/1940.40/5821.20."""
    batch = _dprp_batch()
    a = _investment(batch, "A", "2000.00")
    b = _investment(batch, "B", "2000.00")
    c = _investment(batch, "C", "6000.00")
    SharesTransferService.apply_to_batch(batch, db.session, entry_fee_percent="2", total_transaction_cost_usd="98")
    db.session.expire_all()
    return Batch.query.get(batch.id), a, b, c


class TestSharesDeploymentWorkedExamples:

    def test_fully_subscribed_everyone_gets_max_shares(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                investments = [db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id)]

                rows, totals = SharesDeploymentService.calculate(investments, "1500", "525", "30000")
                by_code = {r.investment.internal_client_code: r for r in rows}

                assert by_code["A"].net_ngn == Decimal("2910600.00")
                assert by_code["B"].net_ngn == Decimal("2910600.00")
                assert by_code["C"].net_ngn == Decimal("8731800.00")

                assert by_code["A"].max_shares == 5544
                assert by_code["B"].max_shares == 5544
                assert by_code["C"].max_shares == 16632
                assert totals["total_demand_shares"] == 27720

                assert not totals["is_oversubscribed"]
                assert by_code["A"].allocated_shares == 5544
                assert by_code["B"].allocated_shares == 5544
                assert by_code["C"].allocated_shares == 16632
                assert totals["unallocated_shares"] == 2280

                assert by_code["A"].refund_usd == Decimal("0.00")
                assert by_code["B"].refund_usd == Decimal("0.00")
                assert by_code["C"].refund_usd == Decimal("0.00")
                assert totals["total_refund_usd"] == Decimal("0.00")
            finally:
                db.session.remove()
                db.drop_all()

    def test_oversubscribed_both_rounds(self, app):
        """shares_allocated=20000 -> A 5544, B 5544, C 8912; refund C = 2702.00 USD."""
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                investments = [db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id)]

                rows, totals = SharesDeploymentService.calculate(investments, "1500", "525", "20000")
                by_code = {r.investment.internal_client_code: r for r in rows}

                assert totals["is_oversubscribed"]
                assert by_code["A"].tier1_shares == 5544
                assert by_code["B"].tier1_shares == 5544
                assert by_code["C"].tier1_shares == 5544

                assert by_code["A"].allocated_shares == 5544
                assert by_code["B"].allocated_shares == 5544
                assert by_code["C"].allocated_shares == 8912
                assert totals["total_allocated_shares"] == 20000
                assert totals["unallocated_shares"] == 0

                assert by_code["A"].refund_usd == Decimal("0.00")
                assert by_code["B"].refund_usd == Decimal("0.00")
                assert by_code["C"].refund_usd == Decimal("2702.00")
            finally:
                db.session.remove()
                db.drop_all()

    def test_oversubscribed_below_minimums_pro_rata(self, app):
        """shares_allocated=10000 (below sum of tier-1 minimums 16632) -> pro-rata 3333 each, 1 unallocated."""
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                investments = [db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id)]

                rows, totals = SharesDeploymentService.calculate(investments, "1500", "525", "10000")
                by_code = {r.investment.internal_client_code: r for r in rows}

                assert totals["is_oversubscribed"]
                assert by_code["A"].allocated_shares == 3333
                assert by_code["B"].allocated_shares == 3333
                assert by_code["C"].allocated_shares == 3333
                assert by_code["A"].round2_shares == 0  # Round 2 skipped entirely
                assert totals["total_allocated_shares"] == 9999
                assert totals["unallocated_shares"] == 1

                assert by_code["A"].refund_usd == Decimal("773.85")
                assert by_code["B"].refund_usd == Decimal("773.85")
                assert by_code["C"].refund_usd == Decimal("4654.65")
            finally:
                db.session.remove()
                db.drop_all()


class TestSharesDeploymentValidation:

    def test_invalid_inputs_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                investments = [db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id)]

                with pytest.raises(SharesDeploymentError):
                    SharesDeploymentService.calculate(investments, "0", "525", "30000")  # rate must be > 0
                with pytest.raises(SharesDeploymentError):
                    SharesDeploymentService.calculate(investments, "1500", "0", "30000")  # price must be > 0
                with pytest.raises(SharesDeploymentError):
                    SharesDeploymentService.calculate(investments, "1500", "525", "0")  # shares must be > 0
                with pytest.raises(SharesDeploymentError):
                    SharesDeploymentService.calculate(investments, "1500", "525", "100.5")  # must be whole
                with pytest.raises(SharesDeploymentError):
                    SharesDeploymentService.calculate(investments, "-1500", "525", "30000")
            finally:
                db.session.remove()
                db.drop_all()

    def test_not_yet_transferred_rejected(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                a = _investment(batch, "A", "2000.00")  # never transferred
                with pytest.raises(SharesDeploymentError):
                    SharesDeploymentService.calculate([a], "1500", "525", "100")
            finally:
                db.session.remove()
                db.drop_all()

    def test_investor_below_minimum_deposit_handled_gracefully(self, app):
        """
        MIN_DEPOSIT_USD is enforced at add-time AND at Transfer (Task 2), so a
        deposit can't reach Deployed below *today's* minimum — but the minimum
        is a config value that can change. If it's raised after an investor has
        already transferred at the old (lower) minimum, their net_usd can end
        up below a MIN_DEPOSIT_USD depositor's net_usd by the time of
        deployment. That must not crash the tier-1 calculation: MIN() just uses
        their own smaller amount, capping their tier-1 share at what they
        actually deposited — never more than they're entitled to.
        """
        with app.app_context():
            db.create_all()
            try:
                batch = _dprp_batch()
                small = _investment(batch, "SMALL", "500.00")  # below today's 2000 minimum
                big = _investment(batch, "BIG", "10000.00")

                # Transfer while the minimum doesn't apply (0), simulating "SMALL
                # deposited back when MIN_DEPOSIT_USD was lower than it is now".
                app.config["MIN_DEPOSIT_USD"] = Decimal("0")
                try:
                    SharesTransferService.apply_to_batch(batch, db.session, entry_fee_percent="0", total_transaction_cost_usd="0")
                finally:
                    app.config["MIN_DEPOSIT_USD"] = Decimal("2000")  # minimum raised back before deployment

                db.session.expire_all()
                small = db.session.get(Investment, small.id)
                big = db.session.get(Investment, big.id)

                # Allocate very few shares so this is oversubscribed, exercising tier-1.
                rows, totals = SharesDeploymentService.calculate([small, big], "1500", "525", "5")
                by_code = {r.investment.internal_client_code: r for r in rows}

                # SMALL's own net_ngn (500*1500=750000) is below a 2000-min-deposit's
                # net_ngn (2000*1500=3000000) -> tier1 capped at SMALL's own amount.
                assert by_code["SMALL"].tier1_shares == by_code["SMALL"].max_shares
                assert by_code["SMALL"].tier1_shares < by_code["BIG"].tier1_shares
            finally:
                db.session.remove()
                db.drop_all()


class TestSharesDeploymentIdempotency:

    def test_rerunning_apply_with_same_inputs_gives_same_result(self, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()

                result1 = SharesDeploymentService.apply_to_batch(
                    Batch.query.get(batch.id), db.session, "1500", "525", "20000"
                )
                db.session.expire_all()
                a1, b1, c1 = (db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id))
                snapshot1 = [(a1.shares_owned, a1.oversubscription_refund_amount),
                             (b1.shares_owned, b1.oversubscription_refund_amount),
                             (c1.shares_owned, c1.oversubscription_refund_amount)]

                # Re-run with the SAME inputs (simulating a retry before the batch is locked).
                result2 = SharesDeploymentService.apply_to_batch(
                    Batch.query.get(batch.id), db.session, "1500", "525", "20000"
                )
                db.session.expire_all()
                a2, b2, c2 = (db.session.get(Investment, a.id), db.session.get(Investment, b.id), db.session.get(Investment, c.id))
                snapshot2 = [(a2.shares_owned, a2.oversubscription_refund_amount),
                             (b2.shares_owned, b2.oversubscription_refund_amount),
                             (c2.shares_owned, c2.oversubscription_refund_amount)]

                assert snapshot1 == snapshot2
                assert result1["total_allocated_shares"] == result2["total_allocated_shares"]
                assert result1["total_refund_usd"] == result2["total_refund_usd"]

                # No duplicate refund Withdrawal rows were created on the re-run.
                refunds = Withdrawal.query.filter_by(
                    batch_id=batch.id, source=WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND
                ).all()
                assert len({r.internal_client_code for r in refunds}) == len(refunds) == 1  # only C was refunded
            finally:
                db.session.remove()
                db.drop_all()


class TestSharesDeploymentApi:

    def test_preview_endpoint_matches_worked_example(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                resp = client.get(
                    f'/api/v1/batches/{batch.id}/shares-deployment-preview'
                    f'?exchange_rate=1500&price_per_share_ngn=525&shares_allocated=20000',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 200
                data = resp.get_json()["data"]
                assert data["banner"] == "Oversubscribed"
                assert data["totals"]["total_refund_usd"] == pytest.approx(2702.00)

                db.session.expire_all()
                assert Batch.query.get(batch.id).deployment_confirmed is False  # dry run only
            finally:
                db.session.remove()
                db.drop_all()

    def test_deploy_applies_allocation_and_locks(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()

                payload = {
                    "deployment_confirmed": True,
                    "date_deployed": "2026-04-01T00:00:00",
                    "exchange_rate": 1500,
                    "price_per_share_ngn": 525,
                    "shares_allocated": 20000,
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 200

                db.session.expire_all()
                batch = Batch.query.get(batch.id)
                assert batch.deployment_confirmed is True
                assert batch.is_oversubscribed is True
                assert batch.shares_allocated_total == 20000
                assert batch.total_shares == Decimal("20000")

                c_inv = db.session.get(Investment, c.id)
                assert c_inv.shares_owned == Decimal("8912")
                assert c_inv.oversubscription_refund_amount == Decimal("2702.00")

                refund = Withdrawal.query.filter_by(
                    batch_id=batch.id, source=WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND
                ).first()
                assert refund is not None
                assert refund.status == "Pending"
                assert refund.amount == Decimal("2702.00")

                audit_entry = AuditLog.query.filter_by(action="SHARES_DEPLOYMENT_ALLOCATION", target_id=batch.id).first()
                assert audit_entry is not None
            finally:
                db.session.remove()
                db.drop_all()

    def test_deploy_rejects_invalid_inputs_without_mutating(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                payload = {
                    "deployment_confirmed": True,
                    "date_deployed": "2026-04-01T00:00:00",
                    "exchange_rate": -1,
                    "price_per_share_ngn": 525,
                    "shares_allocated": 20000,
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 400

                db.session.expire_all()
                batch = Batch.query.get(batch.id)
                assert batch.deployment_confirmed is False
                assert batch.date_deployed is None
            finally:
                db.session.remove()
                db.drop_all()

    def test_revert_lock_unlocks_rejects_refunds_and_audits(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                batch, a, b, c = _worked_example_batch()
                deploy_payload = {
                    "deployment_confirmed": True,
                    "date_deployed": "2026-04-01T00:00:00",
                    "exchange_rate": 1500,
                    "price_per_share_ngn": 525,
                    "shares_allocated": 20000,
                }
                resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps(deploy_payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 200

                revert_resp = client.patch(
                    f'/api/v1/batches/{batch.id}',
                    data=json.dumps({"deployment_confirmed": False}),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert revert_resp.status_code == 200

                db.session.expire_all()
                batch = Batch.query.get(batch.id)
                assert batch.deployment_confirmed is False
                assert batch.shares_allocated_total is None
                assert batch.total_shares is None

                c_inv = db.session.get(Investment, c.id)
                assert c_inv.shares_owned is None
                assert c_inv.oversubscription_refund_amount == Decimal("0.00")

                refund = Withdrawal.query.filter_by(
                    batch_id=batch.id, source=WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND
                ).first()
                assert refund.status == "Rejected"

                audit_entry = AuditLog.query.filter_by(action="SHARES_DEPLOYMENT_REVERTED", target_id=batch.id).first()
                assert audit_entry is not None
                assert audit_entry.old_value is not None
            finally:
                db.session.remove()
                db.drop_all()

    def test_funds_batch_deployment_unaffected(self, client, auth_token, app):
        """FUNDS (NAV-based) deployment is untouched by any of this."""
        with app.app_context():
            db.create_all()
            try:
                batch = _axiom_batch()
                a = _investment(batch, "A", "1000.00")
                SharesTransferService  # no-op reference, FUNDS doesn't use this service
                resp = client.get(
                    f'/api/v1/batches/{batch.id}/shares-deployment-preview'
                    f'?exchange_rate=1500&price_per_share_ngn=525&shares_allocated=100',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 400  # preview only applies to SHARES
            finally:
                db.session.remove()
                db.drop_all()
