"""
Bulk send by statement type + the "Confirm All can never send unrelated emails" rules.

Run with: pytest tests/test_bulk_send.py -v
"""

from datetime import date, datetime, timezone

import pytest

from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment, PendingEmail, Withdrawal
from tests.test_valuation_date_edit_and_split_rows import _seed, _headers

PREVIEW = "/api/v1/emails/bulk-send/preview"
SEND = "/api/v1/emails/bulk-send"


def _seed_batch(app, *, transferred=False, deployed=True):
    with app.app_context():
        _seed(date(2026, 8, 13), date(2026, 8, 20), [])
        b = db.session.query(Batch).first()
        b.is_transferred = transferred
        b.deployment_confirmed = deployed
        db.session.commit()
        inv = db.session.query(Investment).first()
        return b.id, inv.fund_id, inv.id


def _pending(app, inv_id, batch_id, email_type, status):
    with app.app_context():
        row = PendingEmail(
            batch_id=batch_id, investor_id=inv_id, email_type=email_type, status=status,
            subject="s", body="b", recipient_email="edit@example.com", recipient_name="Edit Investor",
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _status(app, email_id):
    with app.app_context():
        return db.session.get(PendingEmail, email_id).status


@pytest.mark.unit
class TestBulkSendPreview:
    def test_needs_fund_or_batch(self, client, super_admin_auth_token):
        r = client.get(f"{PREVIEW}?kind=deposit", headers=_headers(super_admin_auth_token))
        assert r.status_code == 400

    def test_unknown_kind(self, client, super_admin_auth_token):
        r = client.get(f"{PREVIEW}?kind=nope&batch_id=1", headers=_headers(super_admin_auth_token))
        assert r.status_code == 400

    def test_deposit_preview_lists_investor(self, client, app, super_admin_auth_token):
        batch_id, _fund, _inv = _seed_batch(app)
        r = client.get(f"{PREVIEW}?kind=deposit&batch_id={batch_id}", headers=_headers(super_admin_auth_token))
        assert r.status_code == 200
        d = r.get_json()["data"]
        assert d["counts"]["total"] == 1 and d["counts"]["will_send"] == 1
        assert d["rows"][0]["state"] == "none" and d["rows"][0]["email"] == "edit@example.com"

    def test_transfer_requires_transferred_batch(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app, transferred=False)
        r = client.get(f"{PREVIEW}?kind=transfer&batch_id={batch_id}", headers=_headers(super_admin_auth_token))
        assert r.get_json()["data"]["counts"]["total"] == 0

    def test_deployment_requires_deployed_batch(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app, deployed=False)
        r = client.get(f"{PREVIEW}?kind=deployment&batch_id={batch_id}", headers=_headers(super_admin_auth_token))
        assert r.get_json()["data"]["counts"]["total"] == 0

    def test_already_sent_is_flagged_and_excluded(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Confirmed")
        h = _headers(super_admin_auth_token)
        d = client.get(f"{PREVIEW}?kind=deposit&batch_id={batch_id}", headers=h).get_json()["data"]
        assert d["counts"]["already_sent"] == 1 and d["counts"]["will_send"] == 0
        d = client.get(f"{PREVIEW}?kind=deposit&batch_id={batch_id}&include_sent=true", headers=h).get_json()["data"]
        assert d["counts"]["will_send"] == 1


@pytest.mark.unit
class TestBulkSendQueue:
    def test_expected_count_is_required(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app)
        r = client.post(SEND, json={"kind": "deposit", "batch_id": batch_id}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 400

    def test_mismatched_count_queues_nothing(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app)
        r = client.post(SEND, json={"kind": "deposit", "batch_id": batch_id, "expected_count": 99}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 409
        with app.app_context():
            assert db.session.query(PendingEmail).count() == 0

    def test_creates_queued_rows_for_exactly_the_selection(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app)
        r = client.post(SEND, json={"kind": "deposit", "batch_id": batch_id, "expected_count": 1}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert data["created"] == 1 and data["requeued"] == 0 and len(data["email_ids"]) == 1
        with app.app_context():
            row = db.session.get(PendingEmail, data["email_ids"][0])
            assert row.status == "Queued" and row.email_type == "DEPOSIT_CONFIRMATION" and row.queued_at is not None
            assert row.batch_id == batch_id and "Deposit Received" in row.subject

    def test_existing_pending_row_is_reused_not_duplicated(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        existing = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Pending_Confirmation")
        r = client.post(SEND, json={"kind": "deposit", "batch_id": batch_id, "expected_count": 1}, headers=_headers(super_admin_auth_token))
        data = r.get_json()["data"]
        assert data["email_ids"] == [existing] and data["requeued"] == 1 and data["created"] == 0
        assert _status(app, existing) == "Queued"

    def test_does_not_touch_other_pending_emails(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        other = _pending(app, inv_id, batch_id, "INVESTOR_STATEMENT", "Pending_Confirmation")
        client.post(SEND, json={"kind": "deposit", "batch_id": batch_id, "expected_count": 1}, headers=_headers(super_admin_auth_token))
        assert _status(app, other) == "Pending_Confirmation"

    def test_in_progress_is_skipped(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Queued")
        r = client.post(SEND, json={"kind": "deposit", "batch_id": batch_id, "expected_count": 0}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 200 and r.get_json()["data"]["email_ids"] == []

    def test_transfer_and_deployment_bodies(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app, transferred=True, deployed=True)
        h = _headers(super_admin_auth_token)
        for kind, etype, word in (("transfer", "OFFSHORE_TRANSFER", "Transferred"), ("deployment", "INVESTMENT_ACTIVE", "Deployed")):
            r = client.post(SEND, json={"kind": kind, "batch_id": batch_id, "expected_count": 1}, headers=h)
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                row = db.session.get(PendingEmail, r.get_json()["data"]["email_ids"][0])
                assert row.email_type == etype and word in row.subject

    def test_withdrawal_kind_maps_status_to_email_type(self, client, app, super_admin_auth_token):
        batch_id, fund_id, _i = _seed_batch(app)
        with app.app_context():
            db.session.add(Withdrawal(internal_client_code="EDIT-1", fund_id=fund_id, amount=100, status="Pending"))
            db.session.add(Withdrawal(internal_client_code="EDIT-1", fund_id=fund_id, amount=200, status="Approved"))
            db.session.commit()
        h = _headers(super_admin_auth_token)
        d = client.get(f"{PREVIEW}?kind=withdrawal&fund_id={fund_id}", headers=h).get_json()["data"]
        assert d["counts"]["total"] == 2
        assert sorted(r["email_type"] for r in d["rows"]) == ["WITHDRAWAL_APPROVED", "WITHDRAWAL_RECEIVED"]
        r = client.post(SEND, json={"kind": "withdrawal", "fund_id": fund_id, "expected_count": 2}, headers=h)
        assert r.status_code == 200 and r.get_json()["data"]["created"] == 2

    def test_status_counts_only_for_given_ids(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        a = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Queued")
        _pending(app, inv_id, batch_id, "OFFSHORE_TRANSFER", "Confirmed")
        r = client.post("/api/v1/emails/status-counts", json={"ids": [a]}, headers=_headers(super_admin_auth_token))
        assert r.get_json()["data"] == {"total": 1, "counts": {"Queued": 1}}


@pytest.mark.unit
class TestConfirmAllGuard:
    URL = "/api/v1/emails/confirm-all"

    def test_requires_expected_count(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        pid = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Pending_Confirmation")
        r = client.post(self.URL, json={}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 400
        assert _status(app, pid) == "Pending_Confirmation"

    def test_wrong_count_does_nothing(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        pid = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Pending_Confirmation")
        r = client.post(self.URL, json={"expected_count": 5}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 409
        assert _status(app, pid) == "Pending_Confirmation"

    def test_only_pending_and_only_chosen_type(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        dep = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Pending_Confirmation")
        stm = _pending(app, inv_id, batch_id, "INVESTOR_STATEMENT", "Pending_Confirmation")
        sup = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Suppressed")
        fail = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Failed")
        r = client.post(self.URL, json={"email_type": "DEPOSIT_CONFIRMATION", "expected_count": 1}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 200 and r.get_json()["data"]["queued"] == 1
        assert _status(app, dep) == "Queued"
        assert _status(app, stm) == "Pending_Confirmation"
        assert _status(app, sup) == "Suppressed"
        assert _status(app, fail) == "Failed"

    def test_inbox_type_filter_and_counts(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Pending_Confirmation")
        _pending(app, inv_id, batch_id, "INVESTOR_STATEMENT", "Pending_Confirmation")
        h = _headers(super_admin_auth_token)
        d = client.get("/api/v1/emails/inbox?email_type=INVESTOR_STATEMENT", headers=h).get_json()
        assert d["status_counts"] == {"Pending_Confirmation": 1}
        assert d["type_counts"] == {"DEPOSIT_CONFIRMATION": 1, "INVESTOR_STATEMENT": 1}


@pytest.mark.unit
class TestQueueBatchReturnsIds:
    def test_returns_the_created_email_ids(self, client, app, super_admin_auth_token):
        _seed_batch(app)
        r = client.post(
            "/api/v1/emails/statements/queue-batch", json={"client_codes": ["EDIT-1"]},
            headers=_headers(super_admin_auth_token),
        )
        assert r.status_code == 200
        emails = r.get_json()["data"]["emails"]
        assert len(emails) == 1 and emails[0]["client_code"] == "EDIT-1" and emails[0]["recipient_email"] == "edit@example.com"
        with app.app_context():
            assert db.session.get(PendingEmail, emails[0]["id"]).status == "Pending_Confirmation"


@pytest.mark.unit
class TestPreviewEmailAndStatement:
    def _code(self, app):
        with app.app_context():
            return db.session.query(Investment).first().internal_client_code

    def test_sample_returns_exact_email_and_attachment_name(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app, transferred=True)
        code = self._code(app)
        r = client.get(f"{SEND}/sample?kind=transfer&batch_id={batch_id}&client_code={code}", headers=_headers(super_admin_auth_token))
        assert r.status_code == 200
        d = r.get_json()["data"]
        assert d["to"] == "edit@example.com" and "Transferred" in d["subject"]
        assert d["attachment_name"] == f"transfer-confirmation-{code}-{batch_id}.pdf"
        assert "<html" in d["html"].lower()

    def test_sample_unknown_investor_is_404(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app)
        r = client.get(f"{SEND}/sample?kind=deposit&batch_id={batch_id}&client_code=NOPE", headers=_headers(super_admin_auth_token))
        assert r.status_code == 404

    def test_sample_pdf_is_a_pdf_and_sends_nothing(self, client, app, super_admin_auth_token):
        batch_id, _f, _i = _seed_batch(app)
        code = self._code(app)
        r = client.get(f"{SEND}/sample-pdf?kind=deployment&batch_id={batch_id}&client_code={code}", headers=_headers(super_admin_auth_token))
        assert r.status_code == 200 and r.data[:4] == b"%PDF"
        with app.app_context():
            assert db.session.query(PendingEmail).count() == 0

    def test_resend_one_investor_creates_a_fresh_queued_copy(self, client, app, super_admin_auth_token):
        batch_id, _f, inv_id = _seed_batch(app)
        old = _pending(app, inv_id, batch_id, "DEPOSIT_CONFIRMATION", "Confirmed")
        code = self._code(app)
        h = _headers(super_admin_auth_token)
        r = client.post(SEND, json={"kind": "deposit", "batch_id": batch_id, "include_sent": True, "client_code": code, "expected_count": 1}, headers=h)
        assert r.status_code == 200
        ids = r.get_json()["data"]["email_ids"]
        assert len(ids) == 1 and ids[0] != old
        assert _status(app, old) == "Confirmed" and _status(app, ids[0]) == "Queued"
