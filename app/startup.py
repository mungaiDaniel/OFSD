"""Background services started once per server process."""
import logging
from datetime import datetime, timezone

from app.database.database import db
from app.logic.backup_scheduler_service import BackupSchedulerService
from app.logic.batch_scheduler_service import BatchSchedulerService
from app.logic.email_queue_scheduler_service import EmailQueueSchedulerService

log = logging.getLogger(__name__)


def _recover_bulk_upload_jobs(app) -> None:
    # Recover bulk-upload commit jobs from before a restart. APScheduler's
    # BackgroundScheduler is in-memory only — a job scheduled with
    # trigger="date" that hasn't fired yet is simply gone after a restart/deploy.
    # A 'running' job means it was actually interrupted mid-commit: some rows
    # in it may already be committed, so it's marked 'failed' rather than
    # silently re-run (which would risk double-committing the rows that made
    # it through before the restart). A 'queued' job never started, so nothing
    # was written for it yet — safe to just re-schedule from scratch.
    try:
        from app.BulkUpload.model import BulkUploadJob
        from app.BulkUpload.route import _run_bulk_upload_commit_job
        interrupted = db.session.query(BulkUploadJob).filter(BulkUploadJob.status == "running").all()
        for job in interrupted:
            job.status = "failed"
            job.error_message = (
                "Interrupted by a server restart. processed_rows/succeeded_count "
                "show how far it got — check those rows exist before re-uploading "
                "the remainder, to avoid double-creating them."
            )
            job.completed_at = datetime.now(timezone.utc)
        requeued = db.session.query(BulkUploadJob).filter(BulkUploadJob.status == "queued").all()
        db.session.commit()
        for job in requeued:
            BatchSchedulerService.scheduler.add_job(
                func=_run_bulk_upload_commit_job,
                args=[app, job.id],
                trigger="date",
                run_date=datetime.now(timezone.utc),
                id=f"bulk_upload_job_{job.id}",
                misfire_grace_time=3600,
                max_instances=1,
                replace_existing=True,
            )
        if interrupted or requeued:
            log.info("Bulk upload job recovery: %d marked failed (interrupted), %d re-scheduled", len(interrupted), len(requeued))
    except Exception as e:
        log.exception("Bulk upload job recovery failed")


def start_background_services(app) -> None:
    """Start the batch, backup (opt-in) and email-queue schedulers, then recover jobs."""
    for name, service, enabled in (
        ("Batch scheduler", BatchSchedulerService, True),
        ("Backup scheduler", BackupSchedulerService, app.config.get("DB_BACKUP_ENABLED")),
        ("Email queue scheduler", EmailQueueSchedulerService, True),
    ):
        if not enabled:
            continue
        try:
            service.init_scheduler(app)
            log.info("%s initialized", name)
        except Exception:
            log.exception("%s initialization failed", name)
    _recover_bulk_upload_jobs(app)
