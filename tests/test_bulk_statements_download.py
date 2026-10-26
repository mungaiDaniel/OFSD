"""
Bulk statement download: one zip with every selected client's statement PDF.

Run with: pytest tests/test_bulk_statements_download.py -v
"""

import io
import json
import time
import zipfile
from datetime import date

import pytest

from app.database.database import db
from app.Batch.model import Batch
from tests.test_valuation_date_edit_and_split_rows import _seed, _add_second_client, _headers


def _wait_done(client, token, job_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/v1/emails/statements/download-batch/{job_id}", headers=_headers(token))
        d = r.get_json()["data"]
        if d["state"] != "running":
            return d
        time.sleep(0.5)
    raise AssertionError("job did not finish")


@pytest.mark.unit
class TestBulkStatementsDownload:
    def test_zip_has_one_pdf_per_client_and_lists_failures(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id = _seed(date(2026, 8, 13), date(2026, 8, 20), [date(2026, 9, 10)])
            b = db.session.query(Batch).first()
            _add_second_client(b.id, b.share_class.core_fund_id, sc_id, date(2026, 8, 14), date(2026, 8, 20))
        h = _headers(super_admin_auth_token)
        r = client.post(
            "/api/v1/emails/statements/download-batch",
            data=json.dumps({"client_codes": ["EDIT-1", "EDIT-2", "edit-1", "NOPE-9"]}), headers=h,
        )
        assert r.status_code == 202, r.get_data(as_text=True)
        assert r.get_json()["data"]["total"] == 3  # duplicate (case-insensitive) removed
        job_id = r.get_json()["data"]["job_id"]

        status = _wait_done(client, super_admin_auth_token, job_id)
        assert status["state"] == "completed" and status["done"] == 3
        assert [f["client_code"] for f in status["failed"]] == ["NOPE-9"]

        f = client.get(f"/api/v1/emails/statements/download-batch/{job_id}/file", headers=h)
        assert f.status_code == 200 and f.mimetype == "application/zip"
        names = zipfile.ZipFile(io.BytesIO(f.data)).namelist()
        pdfs = [n for n in names if n.endswith(".pdf")]
        assert len(pdfs) == 2 and "_FAILED.txt" in names
        assert any("Edit Investor" in n for n in pdfs) and any("Second Client" in n for n in pdfs)
        assert zipfile.ZipFile(io.BytesIO(f.data)).read(pdfs[0])[:4] == b"%PDF"

    def test_validation_and_unknown_job(self, client, app, super_admin_auth_token):
        h = _headers(super_admin_auth_token)
        assert client.post("/api/v1/emails/statements/download-batch", data=json.dumps({}), headers=h).status_code == 400
        assert client.post("/api/v1/emails/statements/download-batch", data=json.dumps({"client_codes": ["A"], "fund_ids": ["x"]}), headers=h).status_code == 400
        assert client.get("/api/v1/emails/statements/download-batch/" + "0" * 32, headers=h).status_code == 404
        assert client.get("/api/v1/emails/statements/download-batch/../../etc/passwd/file", headers=h).status_code == 404
        assert client.get("/api/v1/emails/statements/download-batch/not-a-job-id/file", headers=h).status_code == 404
