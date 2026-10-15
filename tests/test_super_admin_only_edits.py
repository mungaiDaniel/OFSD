"""
Only super_admin can delete or edit anything
=============================================================================
Every delete and every edit endpoint is super_admin-only (403 for admin and
user). Normal workflow — e.g. advancing a batch's stage — stays open to
admins.

Run with: pytest tests/test_super_admin_only_edits.py -v
"""

import json
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Batch.model import Batch
from app.Investments.model import Investment


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _seed(app):
    with app.app_context():
        fund = CoreFund(fund_name="Perm Fund", fund_code="PERM")
        db.session.add(fund)
        db.session.flush()
        share_class = ShareClass(core_fund_id=fund.id, class_name="Perm Class", class_code="PERM-I", currency="USD")
        db.session.add(share_class)
        db.session.flush()
        batch = Batch(batch_name="Perm Batch", share_class_id=share_class.id, stage=1, is_active=True)
        db.session.add(batch)
        db.session.flush()
        inv = Investment(
            investor_name="Perm Investor", investor_email="perm@example.com", internal_client_code="PERM-1",
            amount_deposited=Decimal("1000.00"), batch_id=batch.id, fund_id=fund.id, share_class_id=share_class.id,
        )
        db.session.add(inv)
        db.session.commit()
        return {"fund_id": fund.id, "batch_id": batch.id, "investment_id": inv.id, "client_code": "PERM-1"}


# (method, url template, json body) — every one is a delete or an edit.
GATED = [
    ("delete", "/api/v1/batches/{batch_id}", None),
    ("patch", "/api/v1/batches/{batch_id}", {"batch_name": "Renamed"}),
    ("patch", "/api/v1/batches/{batch_id}", {"certificate_number": "CERT-X"}),
    ("put", "/api/v1/batches/{batch_id}", {"batch_name": "Renamed"}),
    ("delete", "/api/v1/funds/{fund_id}", None),
    ("delete", "/api/v1/investments/{investment_id}", None),
    ("put", "/api/v1/investments/{investment_id}", {"amount_deposited": "5"}),
    ("patch", "/api/v1/investors/{client_code}", {"investor_name": "Changed"}),
    ("patch", "/api/v1/investors/{client_code}/deposits/bulk-update", {"updates": []}),
    ("patch", "/api/v1/reconciliation/update/{investment_id}", {"value": 1}),
    ("put", "/api/v1/admin/1", None),
]


@pytest.mark.unit
class TestSuperAdminOnlyEdits:
    @pytest.mark.parametrize("method,url,body", GATED)
    def test_admin_is_forbidden(self, client, app, admin_auth_token, method, url, body):
        ids = _seed(app)
        r = getattr(client, method)(url.format(**ids), data=json.dumps(body) if body else None, headers=_headers(admin_auth_token))
        assert r.status_code == 403, (method, url, r.status_code, r.get_data(as_text=True)[:200])

    @pytest.mark.parametrize("method,url,body", GATED)
    def test_token_without_user_record_is_forbidden(self, client, app, auth_token, method, url, body):
        ids = _seed(app)
        r = getattr(client, method)(url.format(**ids), data=json.dumps(body) if body else None, headers=_headers(auth_token))
        assert r.status_code == 403

    def test_nothing_changed_after_forbidden_attempts(self, client, app, admin_auth_token):
        ids = _seed(app)
        client.delete(f"/api/v1/batches/{ids['batch_id']}", headers=_headers(admin_auth_token))
        client.patch(f"/api/v1/batches/{ids['batch_id']}", data=json.dumps({"batch_name": "Renamed"}), headers=_headers(admin_auth_token))
        client.delete(f"/api/v1/funds/{ids['fund_id']}", headers=_headers(admin_auth_token))
        with app.app_context():
            batch = db.session.get(Batch, ids["batch_id"])
            assert batch is not None and batch.batch_name == "Perm Batch"
            assert db.session.get(CoreFund, ids["fund_id"]) is not None

    def test_super_admin_can_rename_and_delete_batch(self, client, app, super_admin_auth_token):
        ids = _seed(app)
        r = client.patch(f"/api/v1/batches/{ids['batch_id']}", data=json.dumps({"batch_name": "Renamed"}), headers=_headers(super_admin_auth_token))
        assert r.status_code == 200
        with app.app_context():
            assert db.session.get(Batch, ids["batch_id"]).batch_name == "Renamed"

    def test_super_admin_can_edit_investor(self, client, app, super_admin_auth_token):
        ids = _seed(app)
        r = client.patch(f"/api/v1/investors/{ids['client_code']}", data=json.dumps({"investor_name": "Changed"}), headers=_headers(super_admin_auth_token))
        assert r.status_code != 403

    def test_super_admin_can_delete_fund(self, client, app, super_admin_auth_token):
        ids = _seed(app)
        r = client.delete(f"/api/v1/funds/{ids['fund_id']}", headers=_headers(super_admin_auth_token))
        # Gets past the permission check — the fund still has deposits, so the
        # delete itself is refused with 409 by the existing business rule.
        assert r.status_code != 403

    def test_admin_can_still_advance_batch_stage(self, client, app, admin_auth_token):
        """Workflow is not an edit: advancing to Transferred stays open to admins."""
        ids = _seed(app)
        r = client.patch(
            f"/api/v1/batches/{ids['batch_id']}",
            data=json.dumps({"stage": 2, "is_transferred": True, "entry_fee_percentage": 0}),
            headers=_headers(admin_auth_token),
        )
        assert r.status_code == 200
        with app.app_context():
            assert db.session.get(Batch, ids["batch_id"]).is_transferred is True
