"""
Bulk statement download: build every selected client's statement PDF in the
background and hand back ONE zip file.

Why a background job: a statement PDF takes a moment to build, so a few hundred
of them would exceed the web server's request timeout if done inside one request.
The job's progress lives in small files on disk (not in memory) so any gunicorn
worker can answer the status / download requests, whichever one started the job.

Layout: <tmp>/ofds_bulk_statements/<job_id>/status.json and statements.zip
"""

import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile

ROOT = os.path.join(tempfile.gettempdir(), "ofds_bulk_statements")
MAX_CLIENTS = 2000
KEEP_SECONDS = 24 * 3600
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n]+')


def job_dir(job_id: str):
    """Directory for a job id, or None if the id isn't a valid job id."""
    if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
        return None
    return os.path.join(ROOT, job_id)


def read_status(job_id: str):
    d = job_dir(job_id)
    if d is None:
        return None
    try:
        with open(os.path.join(d, "status.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def zip_path(job_id: str):
    d = job_dir(job_id)
    return os.path.join(d, "statements.zip") if d else None


def _write_status(d: str, **fields):
    path = os.path.join(d, "status.json")
    try:
        with open(path, encoding="utf-8") as f:
            current = json.load(f)
    except (OSError, ValueError):
        current = {}
    current.update(fields)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f)
    os.replace(tmp, path)  # atomic: a reader never sees a half-written file


def cleanup_old_jobs():
    """Delete job folders older than KEEP_SECONDS."""
    if not os.path.isdir(ROOT):
        return
    cutoff = time.time() - KEEP_SECONDS
    for name in os.listdir(ROOT):
        p = os.path.join(ROOT, name)
        try:
            if os.path.isdir(p) and os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def _unique_name(name: str, code: str, used: set) -> str:
    name = _ILLEGAL.sub(" ", name).strip() or f"{code} - Statement.pdf"
    if name.lower() in used:
        stem, dot, ext = name.rpartition(".")
        name = f"{stem} ({code}).{ext}" if dot else f"{name} ({code})"
    used.add(name.lower())
    return name


def start_job(app, client_codes, build_pdf, filename_for, label=""):
    """
    Start the background job and return its id.

    build_pdf(client_code)    -> BytesIO | ("error", status, message) | None
    filename_for(client_code) -> the PDF's file name inside the zip
    """
    os.makedirs(ROOT, exist_ok=True)
    cleanup_old_jobs()
    job_id = uuid.uuid4().hex
    d = job_dir(job_id)
    os.makedirs(d, exist_ok=True)
    _write_status(d, state="running", total=len(client_codes), done=0, failed=[], label=label,
                  created_at=time.time())
    threading.Thread(
        target=_run, args=(app, job_id, list(client_codes), build_pdf, filename_for), daemon=True
    ).start()
    return job_id


def _run(app, job_id, client_codes, build_pdf, filename_for):
    d = job_dir(job_id)
    part = os.path.join(d, "statements.zip.part")
    failed = []
    used = set()
    with app.app_context():
        from app.database.database import db
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, code in enumerate(client_codes, 1):
                    try:
                        result = build_pdf(code)
                        if result is None:
                            failed.append({"client_code": code, "reason": "could not generate the PDF"})
                        elif isinstance(result, tuple):
                            failed.append({"client_code": code, "reason": str(result[2]) if len(result) > 2 else "error"})
                        else:
                            zf.writestr(_unique_name(filename_for(code), code, used), result.getvalue())
                    except Exception as e:  # one bad client must not stop the rest
                        db.session.rollback()
                        failed.append({"client_code": code, "reason": str(e)[:200]})
                    _write_status(d, done=i, failed=failed)
                if failed:
                    zf.writestr(
                        "_FAILED.txt",
                        "These clients could not be generated:\n"
                        + "\n".join(f"{f['client_code']}: {f['reason']}" for f in failed),
                    )
            os.replace(part, os.path.join(d, "statements.zip"))
            _write_status(d, state="completed", done=len(client_codes), failed=failed)
        except Exception as e:
            _write_status(d, state="failed", error=str(e)[:300], failed=failed)
        finally:
            db.session.remove()
