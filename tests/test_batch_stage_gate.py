"""
New investors may only join a batch that is still at the deposit stage (Stage 1).

Run with: pytest tests/test_batch_stage_gate.py -v
"""

import pytest

from app.database.database import db
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.logic.batch_management_service import BatchManagementService
from tests.test_valuation_date_edit_and_split_rows import _headers


def _class():
    fund = CoreFund(fund_name="Gate Fund", fund_code="GATE")
    db.session.add(fund)
    db.session.flush()
    sc = ShareClass(core_fund_id=fund.id, class_name="Gate Class", class_code="GATE-I", currency="USD")
    db.session.add(sc)
    db.session.flush()
    return fund, sc


def _batch(sc, **kw):
    b = Batch(batch_name=kw.pop("name", "Gate Batch"), share_class_id=sc.id, is_open=True, **kw)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.mark.unit
class TestBatchStageGate:
    def test_deposit_stage_batch_is_reused(self, app):
        with app.app_context():
            _, sc = _class()
            b = _batch(sc, stage=1)
            assert BatchManagementService.find_or_create_batch(sc.id).id == b.id

    @pytest.mark.parametrize("kw", [
        {"stage": 2},
        {"stage": 1, "is_transferred": True},
        {"stage": 3},
        {"stage": 1, "deployment_confirmed": True},
        {"stage": 4, "is_active": True},
    ])
    def test_moved_on_batch_is_never_reused(self, app, kw):
        with app.app_context():
            _, sc = _class()
            old = _batch(sc, **kw)
            assert BatchManagementService.batch_accepts_deposits(old) is False
            got = BatchManagementService.find_or_create_batch(sc.id)
            assert got.id != old.id

    def test_explicit_batch_id_in_transfer_is_rejected(self, client, app, super_admin_auth_token):
        with app.app_context():
            fund, sc = _class()
            b = _batch(sc, stage=2, is_transferred=True)
            fund_id, batch_id = fund.id, b.id
        r = client.post("/api/v1/investments", headers=_headers(super_admin_auth_token), json={
            "investor_name": "Late Investor", "investor_email": "late@example.com",
            "internal_client_code": "LATE-1", "amount_deposited": 1000,
            "fund_id": fund_id, "batch_id": batch_id, "send_email": False,
        })
        assert r.status_code == 400
        assert "cannot be added" in r.get_json()["message"]

    def test_batch_scoped_route_is_rejected_too(self, client, app, super_admin_auth_token):
        with app.app_context():
            fund, sc = _class()
            b = _batch(sc, stage=3, deployment_confirmed=True, is_active=True)
            fund_id, batch_id = fund.id, b.id
        r = client.post(f"/api/v1/batches/{batch_id}/investments", headers=_headers(super_admin_auth_token), json={
            "investor_name": "Late Investor", "investor_email": "late@example.com",
            "internal_client_code": "LATE-2", "amount_deposited": 1000, "fund_id": fund_id, "send_email": False,
        })
        assert r.status_code == 400
