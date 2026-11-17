"""
Transfer statements zip: works before deployment, folder per batch, summary.csv.

Run with: pytest tests/test_transfer_statements_download.py -v
"""

import io
import zipfile
from datetime import date

import pytest

from app.database.database import db
from app.Batch.model import Batch
from tests.test_valuation_date_edit_and_split_rows import _seed, _headers
from tests.test_bulk_statements_download import _wait_done

URL = "/api/v1/emails/transfer-statements/download-batch"


def _download(client, token, job_id):
    r = client.get(f"/api/v1/emails/statements/download-batch/{job_id}/file", headers=_headers(token))
    assert r.status_code == 200
    return r, zipfile.ZipFile(io.BytesIO(r.data))


@pytest.mark.unit
class TestTransferStatementsDownload:
    def test_requires_batch_or_fund(self, client, super_admin_auth_token):
        r = client.post(URL, json={}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 400

    def test_rejects_bad_stage(self, client, super_admin_auth_token):
        r = client.post(URL, json={"batch_ids": [1], "stage": "nope"}, headers=_headers(super_admin_auth_token))
        assert r.status_code == 400

    def test_deployed_batch_only_with_stage_all(self, client, app, super_admin_auth_token):
        with app.app_context():
            _seed(date(2026, 8, 13), date(2026, 8, 20), [date(2026, 9, 10)])
            b = db.session.query(Batch).first()
            b.is_transferred = True
            b.deployment_confirmed = True
            db.session.commit()
            batch_id = b.id
        h = _headers(super_admin_auth_token)

        # Deployed batch is excluded from the default "not yet deployed" view
        r = client.post(URL, json={"batch_ids": [batch_id]}, headers=h)
        assert r.status_code == 404

        r = client.post(URL, json={"batch_ids": [batch_id], "stage": "all"}, headers=h)
        assert r.status_code == 202
        job_id = r.get_json()["data"]["job_id"]
        _wait_done(client, super_admin_auth_token, job_id)
        resp, zf = _download(client, super_admin_auth_token, job_id)
        names = zf.namelist()
        assert "summary.csv" in names
        assert any(n.endswith("Transfer Statement.pdf") and "/" in n for n in names)
        assert "Transfer Statements" in resp.headers["Content-Disposition"]

    def test_undeployed_transferred_batch_is_included(self, client, app, super_admin_auth_token):
        with app.app_context():
            _seed(date(2026, 8, 13), date(2026, 8, 20), [date(2026, 9, 10)])
            b = db.session.query(Batch).first()
            b.is_transferred = True
            b.deployment_confirmed = False
            db.session.commit()
            batch_id = b.id
        h = _headers(super_admin_auth_token)
        r = client.post(URL, json={"batch_ids": [batch_id]}, headers=h)
        assert r.status_code == 202
        job_id = r.get_json()["data"]["job_id"]
        d = _wait_done(client, super_admin_auth_token, job_id)
        assert d["state"] == "completed"
