"""
Bulk Upload Clients — ingest many investors from a spreadsheet, validate them,
and feed them through the SAME creation path as manual "Add Investor" entry
(InvestmentController.create_new_investor / add_existing_investor_deposit),
so batch auto-assignment (BatchManagementService.find_or_create_batch) and the
Stage-1 deposit-confirmation email trigger behave identically to manual entry.

Two-step client flow: POST /validate (dry run, no writes) then POST /commit
(only for rows the user has confirmed). Column mapping is a pure frontend
concern except for remembering the user's last mapping, which is persisted
here (UploadColumnMapping) so repeat uploads of a similarly-shaped file skip
the manual mapping step.
"""
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO

from flask import Blueprint, request, jsonify, make_response, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import insert

from app.database.database import db
from app.Admin.model import User
from app.Investments.model import Investment, PendingEmail
from app.Investments.controllers import InvestmentController
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.BulkUpload.model import UploadColumnMapping, BulkUploadJob
from app.utils.audit_log import create_audit_log, AuditLog, get_client_ip, get_user_identity_meta
from app.logic.batch_management_service import BatchManagementService


bulk_upload_v1 = Blueprint("bulk_upload_v1", __name__, url_prefix="/")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TEMPLATE_HEADERS = [
    "Client Code", "Client Name", "Email", "Phone",
    "Fund Invested In", "Share Class", "Amount Deposited", "Date Deposited",
]

# system_field -> whether it's required for a row to be committable
REQUIRED_FIELDS = {
    "client_code": True,
    "investor_name": True,
    "investor_email": True,
    "investor_phone": False,
    "fund_name": False,  # display/sanity-check only; share_class_code is authoritative
    "share_class_code": True,
    "deposit_amount": True,
    "deposit_date": True,
}


def _current_user():
    identity = get_jwt_identity()
    email = identity if isinstance(identity, str) else (identity or {}).get("email")
    if not email:
        return None
    return db.session.query(User).filter(db.func.lower(User.email) == str(email).strip().lower()).first()


def _template_key(headers: list[str]) -> str:
    normalized = sorted(h.strip().lower() for h in headers if h and h.strip())
    return hashlib.sha256("|".join(normalized).encode("utf-8")).hexdigest()[:32]


@bulk_upload_v1.route("/api/v1/bulk-upload/template", methods=["GET"])
@jwt_required()
def download_template():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(TEMPLATE_HEADERS)
    writer.writerow([
        "41238", "Daniel Mungai", "daniel@example.com", "+254700000000",
        "AXIOM AFRICA EQUITY FUND", "USD_I", "2000.00", "09/18/2026",
    ])
    buf = BytesIO(output.getvalue().encode("utf-8"))
    return send_file(
        buf, mimetype="text/csv", as_attachment=True,
        download_name="bulk_upload_template.csv",
    )


@bulk_upload_v1.route("/api/v1/bulk-upload/mapping", methods=["GET"])
@jwt_required()
def get_mapping():
    user = _current_user()
    if not user:
        return make_response(jsonify({"status": 401, "message": "User not found"}), 401)

    headers_raw = request.args.get("headers", "")
    headers = [h for h in headers_raw.split("||") if h]
    if not headers:
        return make_response(jsonify({"status": 400, "message": "headers query param required (pipe-pipe separated)"}), 400)

    key = _template_key(headers)
    row = (
        db.session.query(UploadColumnMapping)
        .filter(UploadColumnMapping.user_id == user.id, UploadColumnMapping.template_key == key)
        .first()
    )
    return make_response(jsonify({"status": 200, "data": row.to_dict() if row else None}), 200)


@bulk_upload_v1.route("/api/v1/bulk-upload/mapping", methods=["POST"])
@jwt_required()
def save_mapping():
    user = _current_user()
    if not user:
        return make_response(jsonify({"status": 401, "message": "User not found"}), 401)

    data = request.get_json(silent=True) or {}
    headers = data.get("source_headers") or []
    mapping = data.get("mapping") or {}
    if not headers or not mapping:
        return make_response(jsonify({"status": 400, "message": "source_headers and mapping are required"}), 400)

    key = _template_key(headers)
    row = (
        db.session.query(UploadColumnMapping)
        .filter(UploadColumnMapping.user_id == user.id, UploadColumnMapping.template_key == key)
        .first()
    )
    if row:
        row.source_headers = json.dumps(headers)
        row.mapping_json = json.dumps(mapping)
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = UploadColumnMapping(
            user_id=user.id,
            template_key=key,
            source_headers=json.dumps(headers),
            mapping_json=json.dumps(mapping),
        )
        db.session.add(row)
    db.session.commit()
    return make_response(jsonify({"status": 200, "data": row.to_dict()}), 200)


def _parse_amount(raw):
    if raw is None:
        return None, "Missing"
    s = str(raw).strip().replace(",", "").replace("$", "")
    if not s:
        return None, "Missing"
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None, f"'{raw}' is not a valid number"
    if val <= 0:
        return None, "Must be greater than zero"
    return val, None


def _parse_date(raw):
    if raw is None or str(raw).strip() == "":
        return None, "Missing"
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date(), None
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date(), None
    except ValueError:
        return None, f"'{raw}' is not a recognizable date"


def _validate_row(row: dict, row_index: int, seen_in_file: dict, class_by_code: dict, existing_codes: dict):
    """
    row: {system_field: raw_value} already mapped from spreadsheet columns.
    Returns dict: {row_index, status, errors: [{field, message}], warnings: [...], resolved: {...}}

    status is one of:
      "error"              — validation errors, not committable
      "valid"               — no existing client matches this client_code -> NEW CLIENT
      "existing_new_fund"   — client_code matches an existing client, but they don't
                              currently hold this row's fund -> attach a new position
      "existing_same_fund"  — client_code matches AND they already hold a position in
                              this exact fund -> needs an explicit admin decision
                              ("additional_deposit" or "skip") before it can commit;
                              see commit_rows, which defaults to "skip" if none is given.

    Matching is by internal_client_code only — the exact same (and only) identity
    key the manual Add Investor flow uses (InvestmentController.create_new_investor
    raising IntegrityError on a colliding client_code; add_existing_investor_deposit
    looking a client up by client_code). There is no email/phone/name fuzzy matching
    here or in the manual flow, so bulk upload doesn't invent one.
    """
    errors = []
    warnings = []

    def val(field):
        return (row.get(field) or "").strip() if isinstance(row.get(field), str) else row.get(field)

    client_code = val("client_code")
    investor_name = val("investor_name")
    investor_email = val("investor_email")
    investor_phone = val("investor_phone") or None
    fund_name_raw = val("fund_name") or None
    share_class_code = val("share_class_code")
    amount_raw = row.get("deposit_amount")
    date_raw = row.get("deposit_date")

    for field, label in (
        ("client_code", "Client Code"), ("investor_name", "Client Name"),
        ("investor_email", "Email"), ("share_class_code", "Share Class"),
    ):
        if not val(field):
            errors.append({"field": field, "message": f"{label} is required"})

    if investor_email and not EMAIL_RE.match(investor_email):
        errors.append({"field": "investor_email", "message": f"'{investor_email}' is not a valid email address"})

    amount, amount_err = _parse_amount(amount_raw)
    if amount_err:
        errors.append({"field": "deposit_amount", "message": amount_err})

    deposit_date, date_err = _parse_date(date_raw)
    if date_err:
        errors.append({"field": "deposit_date", "message": date_err})

    share_class = class_by_code.get((share_class_code or "").strip().lower()) if share_class_code else None
    if share_class_code and not share_class:
        errors.append({"field": "share_class_code", "message": f"'{share_class_code}' does not match any known share class"})
    if share_class and fund_name_raw:
        if fund_name_raw.strip().lower() != (share_class["fund_name"] or "").strip().lower():
            warnings.append({
                "field": "fund_name",
                "message": f"'{fund_name_raw}' doesn't match the fund for share class {share_class_code} ({share_class['fund_name']}) — the share class will be used, fund name is ignored",
            })

    # Intra-file duplicate: identical code + amount + date seen already in this upload.
    dup_key = (client_code, str(amount) if amount is not None else None, str(deposit_date) if deposit_date else None)
    is_file_duplicate = client_code and dup_key in seen_in_file
    if is_file_duplicate:
        warnings.append({
            "field": "client_code",
            "message": f"Identical row (same code, amount, and date) already appears at row {seen_in_file[dup_key]} in this file — check for a copy-paste error",
        })
    elif client_code:
        seen_in_file[dup_key] = row_index

    existing = existing_codes.get((client_code or "").strip().lower()) if client_code else None
    resolved_fund_id = share_class["fund_id"] if share_class else None

    if errors:
        status = "error"
    elif not existing:
        status = "valid"
    elif resolved_fund_id is not None and resolved_fund_id in existing.get("fund_ids", set()):
        status = "existing_same_fund"
    else:
        status = "existing_new_fund"

    resolved = {
        "client_code": client_code,
        "investor_name": existing["investor_name"] if existing else investor_name,
        "investor_email": existing["investor_email"] if existing else investor_email,
        "investor_phone": (existing["investor_phone"] if existing else investor_phone),
        "fund_id": resolved_fund_id,
        "fund_name": share_class["fund_name"] if share_class else fund_name_raw,
        "share_class_id": share_class["id"] if share_class else None,
        "class_code": share_class["class_code"] if share_class else share_class_code,
        "currency": share_class["currency"] if share_class else None,
        "deposit_amount": float(amount) if amount is not None else None,
        "deposit_date": deposit_date.isoformat() if deposit_date else None,
        # Which fund(s) this client already holds, for the preview's
        # "already holds: X, Y" hint — most useful on an existing_same_fund row.
        "existing_fund_names": sorted(existing.get("fund_names", set())) if existing else [],
    }

    return {
        "row_index": row_index,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "resolved": resolved,
    }


@bulk_upload_v1.route("/api/v1/bulk-upload/validate", methods=["POST"])
@jwt_required()
def validate_rows():
    data = request.get_json(silent=True) or {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return make_response(jsonify({"status": 400, "message": "rows (non-empty list) is required"}), 400)

    active_classes = (
        db.session.query(ShareClass, CoreFund)
        .join(CoreFund, ShareClass.core_fund_id == CoreFund.id)
        .filter(ShareClass.is_active.is_(True))
        .all()
    )
    class_by_code = {
        sc.class_code.strip().lower(): {
            "id": sc.id, "class_code": sc.class_code, "currency": sc.currency,
            "fund_id": cf.id, "fund_name": cf.fund_name,
        }
        for sc, cf in active_classes
    }

    codes_in_file = {
        str(r.get("client_code")).strip().lower()
        for r in rows if r.get("client_code")
    }
    # Indexed lookup — NOT a full-table load: one IN-clause query against
    # ix_investments_lower_client_code (see main.py) rather than pulling every
    # Investment row into Python to compare in memory. A plain btree index on
    # internal_client_code can't serve a lower(...)-wrapped filter, so that
    # functional index is what keeps this an index scan instead of a
    # sequential scan. The result set built from it is only the (small)
    # subset of existing investors who actually appear in the file — every
    # uploaded row is still checked, just against that small in-memory map
    # instead of hitting the DB again per row.
    #
    # Deliberately ONE query, not chunked into batches: measured against a
    # 100k-row upload and a 50k-investor table, splitting this into 1,000-code
    # chunks made it ~3.5x SLOWER (7.3s vs 2.2s) — each chunk's fixed
    # round-trip/query-planning overhead, paid ~100 times over, dwarfs
    # whatever a smaller IN list saves. Postgres has no meaningful limit on
    # IN-list size at this scale, so a single query is both simpler and
    # faster; the functional index is what actually matters as the investor
    # table grows (it flips the plan from a Seq Scan to a Bitmap Index Scan
    # regardless of query shape).
    existing_investments = (
        db.session.query(Investment)
        .filter(db.func.lower(Investment.internal_client_code).in_(codes_in_file))
        .all()
    ) if codes_in_file else []
    existing_codes = {}
    for inv in existing_investments:
        key = inv.internal_client_code.strip().lower()
        entry = existing_codes.setdefault(key, {
            "investor_name": inv.investor_name,
            "investor_email": inv.investor_email,
            "investor_phone": inv.investor_phone,
            # Every fund this client already holds a position in — checked
            # per-row against the upload's resolved fund_id to tell "existing
            # client, new fund" apart from "existing client, same fund"
            # (requirement 2's three-way split), not just "client exists".
            "fund_ids": set(),
            "fund_names": set(),
        })
        if inv.fund_id is not None:
            entry["fund_ids"].add(inv.fund_id)
        if inv.fund_name:
            entry["fund_names"].add(inv.fund_name)

    seen_in_file: dict = {}
    results = [
        _validate_row(row, idx, seen_in_file, class_by_code, existing_codes)
        for idx, row in enumerate(rows)
    ]

    summary = {
        "total": len(results),
        "valid": sum(1 for r in results if r["status"] == "valid"),
        "existing_new_fund": sum(1 for r in results if r["status"] == "existing_new_fund"),
        "existing_same_fund": sum(1 for r in results if r["status"] == "existing_same_fund"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "warnings": sum(1 for r in results if r["warnings"]),
    }
    return make_response(jsonify({"status": 200, "data": {"rows": results, "summary": summary}}), 200)


CHUNK_SIZE = 1500
# Detail lists in the final results payload are capped so a 100k-row job
# doesn't serialize a multi-megabyte JSON blob into one TEXT column — the
# *counts* (succeeded_count/failed_count/skipped_count on the job row) are
# always exact regardless of this cap; only the per-row detail samples are
# limited, and failed/skipped are capped generously since those are what an
# admin actually needs to see to fix something.
RESULTS_SUCCEEDED_SAMPLE_CAP = 200
RESULTS_FAILED_CAP = 5000
RESULTS_SKIPPED_CAP = 5000


@bulk_upload_v1.route("/api/v1/bulk-upload/commit", methods=["POST"])
@jwt_required()
def commit_rows():
    """
    Body: {"filename": "...", "rows": [{"status": "...", "resolved": {...}, "decision": "additional_deposit"|"skip"}]}

    Starts a BACKGROUND job and returns immediately — committing was
    previously done inline in this request, one row at a time through the
    same path the single "Add Investor" button uses (a commit, a spawned
    thread for the deposit-confirmation email, an audit-log commit — per
    row). At 100,000 rows that's 100,000 threads and 300,000+ sequential
    commits in one request, which is what froze the app. See
    _run_bulk_upload_commit_job for the fixed, chunked, bulk-insert version.

    `decision` only matters for status == "existing_same_fund" — the row the
    admin must explicitly resolve (requirement 2c). Any other status is
    unaffected by it. Missing/unrecognized decision on such a row defaults to
    "skip" — this endpoint never silently assumes "additional_deposit" for a
    row the admin didn't actually make a call on, even if the frontend has a
    bug or an older client omits the field.

    Poll GET /api/v1/bulk-upload/jobs/<job_id> for progress and, once
    status is "completed"/"failed", the same {succeeded, failed, skipped}
    shape this endpoint used to return synchronously.
    """
    data = request.get_json(silent=True) or {}
    rows = data.get("rows")
    filename = data.get("filename") or "unknown file"
    if not isinstance(rows, list) or not rows:
        return make_response(jsonify({"status": 400, "message": "rows (non-empty list) is required"}), 400)

    user = _current_user()
    job = BulkUploadJob(
        filename=filename,
        status="queued",
        total_rows=len(rows),
        rows_payload=json.dumps(rows),
        created_by_user_id=user.id if user else None,
        created_by_email=user.email if user else None,
        created_by_name=user.name if user else None,
    )
    db.session.add(job)
    db.session.commit()

    if not _schedule_bulk_upload_job(job.id):
        job.status = "failed"
        job.error_message = "Could not schedule the background job (scheduler unavailable)"
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return make_response(jsonify({"status": 500, "message": "Could not start the bulk upload job"}), 500)

    return make_response(jsonify({
        "status": 202,
        "message": f"Bulk upload job started for {len(rows)} row(s)",
        "data": {"job_id": job.id, "total_rows": job.total_rows, "status": job.status},
    }), 202)


def _schedule_bulk_upload_job(job_id: int) -> bool:
    """Runs _run_bulk_upload_commit_job(job_id) once, immediately.

    Primary path: the app's existing APScheduler BackgroundScheduler (reusing
    the same scheduler the batch-closure/email-queue jobs run on).

    Fallback path: a plain daemon thread. In production Gunicorn deployments
    with multiple worker processes, each worker has its own memory space and
    its own copy of BatchSchedulerService.scheduler — the scheduler is only
    non-None in the worker that actually called init_scheduler(). Workers that
    received the request after a fork see scheduler=None. Rather than returning
    False and letting commit_rows() respond with a 500, we fall back to a
    daemon thread so the job always starts regardless of which Gunicorn worker
    handles the request.
    """
    import threading

    app_obj = current_app._get_current_object()

    # Primary: APScheduler (preferred — uses the managed thread pool)
    try:
        from app.logic.batch_scheduler_service import BatchSchedulerService
        scheduler = BatchSchedulerService.scheduler
        if scheduler is not None:
            scheduler.add_job(
                func=_run_bulk_upload_commit_job,
                args=[app_obj, job_id],
                trigger="date",
                run_date=datetime.now(timezone.utc),
                id=f"bulk_upload_job_{job_id}",
                misfire_grace_time=3600,
                max_instances=1,
                replace_existing=True,
            )
            return True
    except Exception as e:
        print(f"APScheduler unavailable for bulk upload job {job_id} ({e}); falling back to daemon thread")

    # Fallback: daemon thread (safe for multi-worker Gunicorn where the
    # in-memory scheduler is None in workers other than the one that started it)
    try:
        t = threading.Thread(
            target=_run_bulk_upload_commit_job,
            args=[app_obj, job_id],
            daemon=True,
            name=f"bulk_upload_job_{job_id}",
        )
        t.start()
        print(f"Bulk upload job {job_id} started on daemon thread (APScheduler not available in this worker)")
        return True
    except Exception as e:
        print(f"Could not start daemon thread for bulk upload job {job_id}: {e}")
        return False


@bulk_upload_v1.route("/api/v1/bulk-upload/jobs/<int:job_id>", methods=["GET"])
@jwt_required()
def get_bulk_upload_job(job_id):
    job = db.session.query(BulkUploadJob).filter(BulkUploadJob.id == job_id).first()
    if not job:
        return make_response(jsonify({"status": 404, "message": "Job not found"}), 404)

    data = {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows,
        "succeeded_count": job.succeeded_count,
        "failed_count": job.failed_count,
        "skipped_count": job.skipped_count,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }
    if job.status in ("completed", "failed") and job.results_payload:
        try:
            data["results"] = json.loads(job.results_payload)
        except Exception:
            data["results"] = None
    return make_response(jsonify({"status": 200, "data": data}), 200)


def _build_deposit_confirmation_pending_email(*, batch, investment_id, name, email, amount, currency, trigger_source):
    """
    Same DEPOSIT_CONFIRMATION email EmailService._create_pending_email would
    create for this deposit — built directly as a row dict here instead,
    because the normal path (EmailService.send_batch_stage_emails ->
    send_deposit_received_batch) spawns a brand-new OS thread per call. That
    is fine for one deposit; for 100,000 in a bulk upload it is 100,000
    threads, each opening its own DB connection — the other half of why the
    app froze, on top of the per-row commits. Text kept byte-for-byte
    identical to app/utils/email_service.py's manual_approval branch.
    """
    subject = f"Deposit Received - {batch.batch_name}"
    body = f"""Dear {name},

We have successfully received your investment deposit into batch "{batch.batch_name}".

Deposit details
• Capital Amount: {currency} {float(amount):,.2f}
• Status: Deposited (Stage 1/3)

Your funds are now being held securely while we finalize the batch for offshore transfer. You will receive a follow-up email once the transfer has been initiated.

Please find the attached deposit statement for your records.

Best regards,
AXYS INVESTMENT BANK
"""
    return {
        "batch_id": batch.id,
        "investor_id": investment_id,
        "email_type": "DEPOSIT_CONFIRMATION",
        "status": "Pending_Confirmation",
        "subject": subject,
        "body": body,
        "recipient_email": email,
        "recipient_name": name,
        "amount": amount,
        "batch_name": batch.batch_name,
        "currency_type": currency or "USD",
        "trigger_source": trigger_source,
        "created_at": datetime.now(timezone.utc),
    }


def _commit_bulk_upload_chunk(session, chunk, filename, actor_kwargs, existing_identity_by_code, fund_class_cache):
    """
    Processes one chunk (~1,500 rows) of a bulk-upload commit. Fast path:
    every row's data is collected in memory, then ONE core bulk INSERT (with
    RETURNING) creates every Investment row in the chunk and hands back their
    ids in input order; those ids are used to build the PendingEmail and
    AuditLog rows, each written with its own single bulk INSERT; the caller
    commits once for the whole chunk. A handful of DB round-trips total
    instead of 3+ ORM round-trips per row.

    fund_class_cache is keyed by (fund_id, share_class_id) and shared across
    every chunk for the whole job (built lazily here, on first use) — a real
    upload usually targets one or a handful of funds, so this turns what
    would otherwise be 2 SELECTs per row (ShareClass + CoreFund, unchanged
    for the whole job) into 2 SELECTs per DISTINCT fund/class combo. This is
    what actually made a 3,000-row test run 37s: those redundant per-row
    lookups, not the bulk insert itself.

    Batch resolution (BatchManagementService.find_or_create_batch) is the one
    thing still done per row: which batch a deposit lands in is stateful
    (depends on what's already open), so it can't be cached the same way.

    Returns (succeeded, failed, skipped) for this chunk.
    """
    succeeded, failed, skipped = [], [], []
    pending_rows = []  # (investment_obj, batch, name, email, amount, currency, outcome, r)

    for row in chunk:
        r = row.get("resolved") or row
        status = row.get("status")
        client_code = r.get("client_code")

        if status == "existing_same_fund" and row.get("decision") != "additional_deposit":
            skipped.append({"client_code": client_code, "reason": "Possible duplicate (same fund) — no \"additional deposit\" decision was given"})
            continue

        try:
            fund_id = r["fund_id"]
            share_class_id = r["share_class_id"]
            amount = Decimal(str(r["deposit_amount"]))
            deposit_dt = datetime.fromisoformat(r["deposit_date"])
            currency = r.get("currency")

            cache_key = (fund_id, share_class_id)
            if cache_key not in fund_class_cache:
                share_class = session.query(ShareClass).filter(
                    ShareClass.id == share_class_id, ShareClass.core_fund_id == fund_id, ShareClass.is_active == True
                ).first()
                fund = session.query(CoreFund).filter(CoreFund.id == fund_id).first() if share_class else None
                fund_class_cache[cache_key] = (share_class, fund)
            share_class, fund = fund_class_cache[cache_key]
            if not share_class:
                failed.append({"client_code": client_code, "message": "Invalid share_class_id for the specified fund"})
                continue
            if not fund:
                failed.append({"client_code": client_code, "message": "Fund not found"})
                continue

            batch = BatchManagementService.find_or_create_batch(share_class_id)

            if status in ("existing_new_fund", "existing_same_fund"):
                existing = existing_identity_by_code.get((client_code or "").strip().lower())
                name = existing["investor_name"] if existing else r.get("investor_name")
                email = existing["investor_email"] if existing else r.get("investor_email")
                phone = existing["investor_phone"] if existing else r.get("investor_phone")
                outcome = "existing_same_fund_added" if status == "existing_same_fund" else "existing_new_fund"
            else:
                name = r["investor_name"]
                email = r["investor_email"]
                phone = r.get("investor_phone")
                outcome = "new_client"

            investment_dict = {
                "investor_name": name,
                "investor_email": email,
                "investor_phone": phone,
                "internal_client_code": client_code,
                "amount_deposited": amount,
                "date_deposited": deposit_dt,
                "batch_id": batch.id,
                "fund_id": fund_id,
                "fund_name": fund.fund_name,
                "share_class_id": share_class_id,
                "deposit_date": deposit_dt.date(),
                "original_deposit_amount": amount,
                "current_market_value": Decimal("0.00"),
                "currency_type": currency or share_class.currency,
            }
            pending_rows.append((investment_dict, batch, name, email, amount, currency or share_class.currency, outcome, r, client_code))
        except Exception as e:
            failed.append({"client_code": client_code, "message": str(e)})

    # Core bulk INSERT (not one ORM object + session.add() per row, then a
    # flush) — ~2x faster measured on a 1,500-row chunk, and this is by far
    # the highest-row-count insert in the whole job. RETURNING gives back
    # every assigned id, in input order (guaranteed for a single INSERT...
    # VALUES...RETURNING statement), so the ids can be zipped straight back
    # onto pending_rows without a second query.
    investment_ids = []
    if pending_rows:
        investment_dicts = [p[0] for p in pending_rows]
        result = session.execute(insert(Investment).returning(Investment.id), investment_dicts)
        investment_ids = [row[0] for row in result]

    email_rows = []
    audit_rows = []
    now = datetime.now(timezone.utc)
    ip = None
    ua = "BACKGROUND_JOB (bulk-upload commit)"

    for investment_id, (_dict, batch, name, email, amount, currency, outcome, r, client_code) in zip(investment_ids, pending_rows):
        succeeded.append({"client_code": client_code, "investment_id": investment_id})
        email_rows.append(_build_deposit_confirmation_pending_email(
            batch=batch, investment_id=investment_id, name=name, email=email,
            amount=amount, currency=currency, trigger_source="investor_add",
        ))
        audit_rows.append({
            "user_id": actor_kwargs.get("actor_user_id"), "user_email": actor_kwargs.get("actor_user_email"),
            "user_name": actor_kwargs.get("actor_user_name"),
            "action": "BULK_UPLOAD_ROW_RESOLVED", "target_type": "investment", "target_id": investment_id, "target_name": client_code,
            "description": f'Bulk upload "{filename}" row for {client_code}: {outcome}',
            "new_value": json.dumps({
                "outcome": outcome, "fund_id": r.get("fund_id"), "fund_name": r.get("fund_name"),
                "deposit_amount": r.get("deposit_amount"), "deposit_date": r.get("deposit_date"),
            }, default=str),
            "ip_address": ip, "user_agent": ua, "timestamp": now, "success": True,
        })

    for s in skipped:
        audit_rows.append({
            "user_id": actor_kwargs.get("actor_user_id"), "user_email": actor_kwargs.get("actor_user_email"),
            "user_name": actor_kwargs.get("actor_user_name"),
            "action": "BULK_UPLOAD_ROW_RESOLVED", "target_type": "investment", "target_name": s["client_code"],
            "description": f'Bulk upload "{filename}" row for {s["client_code"]}: existing client, same fund — skipped as possible duplicate',
            "new_value": json.dumps({"outcome": "existing_same_fund_skipped"}, default=str),
            "ip_address": ip, "user_agent": ua, "timestamp": now, "success": True,
        })

    if email_rows:
        session.execute(insert(PendingEmail), email_rows)
    if audit_rows:
        session.execute(insert(AuditLog), audit_rows)

    return succeeded, failed, skipped


def _run_bulk_upload_commit_job(app, job_id):
    """
    The background worker for a bulk-upload commit — see commit_rows()'s
    docstring for why this doesn't run inline in the request. Chunks the
    row list, bulk-inserts each chunk (Investment + PendingEmail + AuditLog
    rows) with exactly one commit per chunk, and updates the job's progress
    counters after every chunk so GET .../jobs/<id> reflects real progress
    while it's still running.

    If a whole chunk's flush fails (e.g. a genuinely bad row slipped through
    validation), it falls back to processing that one chunk row-by-row so a
    single bad row can't cost the other ~1,499 good ones in it.
    """
    with app.app_context():
        session = db.session

        # Atomic claim: an UPDATE ... WHERE status='queued' row-locks the job
        # for the duration of the statement, so if this ever ran more than
        # once for the same job_id at the same time — a duplicate
        # scheduler.add_job call, or (in a multi-worker production deployment,
        # where every worker process has its own in-memory scheduler) more
        # than one worker recovering the same interrupted job at startup —
        # only the first UPDATE actually flips it to 'running'; every other
        # caller's UPDATE matches 0 rows and returns immediately instead of
        # re-committing the same rows a second time. A plain
        # "if job.status != 'queued': return" check has a race window between
        # the read and the write that this closes.
        claim = session.execute(
            BulkUploadJob.__table__.update()
            .where(BulkUploadJob.id == job_id, BulkUploadJob.status == "queued")
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        session.commit()
        if claim.rowcount == 0:
            return  # already claimed/processed elsewhere, or job doesn't exist

        job = session.query(BulkUploadJob).filter(BulkUploadJob.id == job_id).first()

        actor_kwargs = {
            "actor_user_id": job.created_by_user_id,
            "actor_user_email": job.created_by_email,
            "actor_user_name": job.created_by_name,
        }

        try:
            rows = json.loads(job.rows_payload)
        except Exception as e:
            job.status = "failed"
            job.error_message = f"Could not parse stored rows: {e}"
            job.completed_at = datetime.now(timezone.utc)
            session.commit()
            return

        # Existing-investor identity (name/email/phone) for existing_new_fund /
        # existing_same_fund rows — ONE indexed query for every such client code
        # across the WHOLE job, not one query per row. These rows use the DB's
        # on-file identity, not whatever the spreadsheet says, matching the
        # single-add flow's existing behavior (add_existing_investor_deposit
        # copies from the existing Investment row rather than trusting new input).
        existing_codes = {
            str((r.get("resolved") or r).get("client_code")).strip().lower()
            for r in rows
            if r.get("status") in ("existing_new_fund", "existing_same_fund") and (r.get("resolved") or r).get("client_code")
        }
        existing_identity_by_code = {}
        if existing_codes:
            for inv in (
                session.query(Investment)
                .filter(db.func.lower(Investment.internal_client_code).in_(existing_codes))
                .all()
            ):
                key = inv.internal_client_code.strip().lower()
                existing_identity_by_code.setdefault(key, {
                    "investor_name": inv.investor_name,
                    "investor_email": inv.investor_email,
                    "investor_phone": inv.investor_phone,
                })

        fund_class_cache = {}  # (fund_id, share_class_id) -> (ShareClass, CoreFund), shared for the whole job
        succeeded, failed, skipped = [], [], []
        try:
            for i in range(0, len(rows), CHUNK_SIZE):
                chunk = rows[i:i + CHUNK_SIZE]
                try:
                    s, f, sk = _commit_bulk_upload_chunk(session, chunk, job.filename, actor_kwargs, existing_identity_by_code, fund_class_cache)
                    session.commit()
                except Exception as chunk_err:
                    session.rollback()
                    print(f"Bulk upload job {job_id}: chunk starting at row {i} failed as a batch ({chunk_err}); "
                          f"falling back to processing it row-by-row")
                    s, f, sk = [], [], []
                    for single_row in chunk:
                        try:
                            rs, rf, rsk = _commit_bulk_upload_chunk(session, [single_row], job.filename, actor_kwargs, existing_identity_by_code, fund_class_cache)
                            session.commit()
                            s.extend(rs); f.extend(rf); sk.extend(rsk)
                        except Exception as row_err:
                            session.rollback()
                            r = single_row.get("resolved") or single_row
                            f.append({"client_code": r.get("client_code"), "message": str(row_err)})

                succeeded.extend(s)
                failed.extend(f)
                skipped.extend(sk)
                job.processed_rows = min(len(rows), i + len(chunk))
                job.succeeded_count = len(succeeded)
                job.failed_count = len(failed)
                job.skipped_count = len(skipped)
                session.commit()

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.results_payload = json.dumps({
                "succeeded_count": len(succeeded),
                "failed_count": len(failed),
                "skipped_count": len(skipped),
                "succeeded_sample": succeeded[:RESULTS_SUCCEEDED_SAMPLE_CAP],
                "failed": failed[:RESULTS_FAILED_CAP],
                "skipped": skipped[:RESULTS_SKIPPED_CAP],
            })
            session.commit()

            create_audit_log(
                action="BULK_UPLOAD_INVESTORS",
                target_type="investment",
                target_name=job.filename,
                description=(
                    f'Bulk upload "{job.filename}": {len(succeeded)} succeeded, {len(failed)} failed, '
                    f'{len(skipped)} skipped (possible duplicates) out of {len(rows)} rows.'
                ),
                new_value={
                    "filename": job.filename, "row_count": len(rows),
                    "succeeded": len(succeeded), "failed": len(failed), "skipped": len(skipped),
                },
                success=len(failed) == 0,
                **actor_kwargs,
            )
        except Exception as e:
            session.rollback()
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            session.commit()
