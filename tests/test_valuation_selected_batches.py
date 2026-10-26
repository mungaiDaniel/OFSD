"""
Valuation for selected batches vs all batches.

- batch_ids omitted/empty  -> all batches (unchanged behaviour)
- batch_ids = [..]         -> only those batches: reconcile against their shares, write
                              snapshots only for them, save the class NAV for the date
- a later All run skips holdings already valued on that date

Run with: pytest tests/test_valuation_selected_batches.py -v
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.model import Batch
from app.Funds.investor_shares import InvestorShares
from app.Funds.nav_history import NavHistory
from app.Investments.model import Investment
from app.Valuation.model import ValuationJob
from app.Valuation.route import _run_valuation_commit_job
from app.Valuation.valuation_snapshot import ValuationSnapshot
from tests.test_valuation_date_edit_and_split_rows import _seed, _utc, _headers

NAV = Decimal("40.00")
VDATE = "2026-10-20"


def _two_batches():
    """Class EDIT-I with batch A (59.1739 shares) and batch B (24.3200 shares)."""
    sc_id = _seed(date(2026, 8, 13), date(2026, 8, 13), [])
    a = db.session.query(Batch).first()
    b = Batch(
        batch_name="Edit Batch B", share_class_id=sc_id, stage=4, is_active=True, deployment_confirmed=True,
        date_deployed=_utc(date(2026, 8, 20)), deployment_date_actual=date(2026, 8, 20), deployment_nav=Decimal("41.12"),
    )
    db.session.add(b)
    db.session.flush()
    inv = Investment(
        investor_name="Second Client", investor_email="second@example.com", internal_client_code="EDIT-2",
        amount_deposited=Decimal("1000.00"), batch_id=b.id, fund_id=a.share_class.core_fund_id, fund_name="Edit Fund",
        share_class_id=sc_id, date_deposited=_utc(date(2026, 8, 14)),
    )
    db.session.add(inv)
    db.session.flush()
    db.session.add(InvestorShares(
        investment_id=inv.id, share_class_id=sc_id, batch_id=b.id,
        shares_owned=Decimal("24.3200"), deployment_nav=Decimal("41.12"), deployment_date=date(2026, 8, 20),
    ))
    db.session.commit()
    return sc_id, a.id, b.id


def _payload(sc_id, total, batch_ids=None, nav=NAV):
    p = {"valuation_date": VDATE, "classes": [{"share_class_id": sc_id, "nav_per_share": str(nav), "total_fund_nav": str(total)}]}
    if batch_ids is not None:
        p["batch_ids"] = batch_ids
    return p


def _run(app, payload):
    job = ValuationJob(status="queued", total_investors=0, request_payload=json.dumps(payload))
    db.session.add(job)
    db.session.commit()
    job_id = job.id
    _run_valuation_commit_job(app, job_id)
    db.session.expire_all()
    return db.session.get(ValuationJob, job_id)


def _total(shares):
    return (Decimal(shares) * NAV).quantize(Decimal("0.01"))


@pytest.mark.unit
class TestSelectedBatchValuation:
    def test_preview_scopes_to_selected_batches(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id, a_id, b_id = _two_batches()
        h = _headers(super_admin_auth_token)
        sel = client.post("/api/v1/valuation/preview", data=json.dumps(_payload(sc_id, _total("59.1739"), [a_id])), headers=h).get_json()["data"]
        assert sel["batch_ids"] == [a_id]
        assert sel["classes"][0]["total_shares"] == 59.1739 and sel["classes"][0]["status"] == "PASS"
        assert [i["client_code"] for i in sel["classes"][0]["investors"]] == ["EDIT-1"]
        allr = client.post("/api/v1/valuation/preview", data=json.dumps(_payload(sc_id, _total("83.4939"))), headers=h).get_json()["data"]
        assert allr["batch_ids"] is None and allr["classes"][0]["total_shares"] == 83.4939 and allr["classes"][0]["status"] == "PASS"

    def test_whole_class_total_fails_for_selected_batches(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id, a_id, _b = _two_batches()
        r = client.post("/api/v1/valuation/preview", data=json.dumps(_payload(sc_id, _total("83.4939"), [a_id])), headers=_headers(super_admin_auth_token))
        assert r.get_json()["data"]["classes"][0]["status"] == "FAIL"

    def test_selected_then_all_skips_already_valued(self, app):
        with app.app_context():
            sc_id, a_id, b_id = _two_batches()
            job = _run(app, _payload(sc_id, _total("59.1739"), [a_id]))
            assert job.status == "completed", job.error_message
            assert job.snapshots_created == 1
            snaps = db.session.query(ValuationSnapshot).all()
            assert len(snaps) == 1 and snaps[0].valuation_date == date(2026, 10, 20)
            nav = db.session.query(NavHistory).filter_by(share_class_id=sc_id, source="valuation").one()
            assert nav.nav_per_share == NAV and nav.total_fund_nav is None  # subset total is not the class total
            assert db.session.get(Batch, b_id).deployment_total_nav is None  # unselected batch untouched

            job2 = _run(app, _payload(sc_id, _total("83.4939")))
            assert job2.status == "completed", job2.error_message
            assert job2.snapshots_created == 1  # only batch B; batch A skipped
            assert json.loads(job2.results_payload)["classes"][0]["already_valued"] == 1
            assert db.session.query(ValuationSnapshot).count() == 2
            nav = db.session.query(NavHistory).filter_by(share_class_id=sc_id, source="valuation").one()
            assert nav.total_fund_nav == _total("83.4939")

    def test_different_nav_on_same_date_is_rejected(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id, a_id, b_id = _two_batches()
            assert _run(app, _payload(sc_id, _total("59.1739"), [a_id])).status == "completed"
        r = client.post("/api/v1/valuation/nav", data=json.dumps(_payload(sc_id, Decimal("24.3200") * Decimal("41"), [b_id], nav=Decimal("41"))), headers=_headers(super_admin_auth_token))
        assert r.status_code == 409 and "already has a valuation" in r.get_json()["message"]

    def test_unknown_batch_rejected(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id, a_id, _b = _two_batches()
        r = client.post("/api/v1/valuation/preview", data=json.dumps(_payload(sc_id, _total("59.1739"), [999999])), headers=_headers(super_admin_auth_token))
        assert r.status_code == 400
