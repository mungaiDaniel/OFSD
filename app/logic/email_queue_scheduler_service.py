"""
Email Send Queue Scheduler — drains PendingEmail rows with status='Queued' at a
fixed, safe rate instead of sending everything the moment it's approved.

Why: confirming an email used to send it immediately, synchronously, inside the
request — fine for one email, but for hundreds/thousands it either blocked the
browser for hours (if done one at a time) or blew past what an Office365 mailbox
will tolerate before throttling/blocking (if done all at once). Now Confirm just
marks an email 'Queued'; this job is the only thing that actually calls SMTP,
draining up to EMAIL_QUEUE_BATCH_SIZE queued emails every EMAIL_QUEUE_INTERVAL_MINUTES
minutes, oldest-approved-first.
"""
import logging

from apscheduler.triggers.interval import IntervalTrigger

from app.logic.batch_scheduler_service import BatchSchedulerService

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 5
DEFAULT_BATCH_SIZE = 100


class EmailQueueSchedulerService:

    @staticmethod
    def init_scheduler(app) -> None:
        scheduler = BatchSchedulerService.scheduler
        if scheduler is None:
            raise RuntimeError("BatchSchedulerService.init_scheduler() must run before EmailQueueSchedulerService")

        # Prefer a DB-saved override (Settings -> Email Queue) over config.py/.env.
        interval_minutes = DEFAULT_INTERVAL_MINUTES
        batch_size = DEFAULT_BATCH_SIZE
        try:
            from app.database.database import db
            from app.Settings.service import get_effective_email_settings
            effective = get_effective_email_settings(app, db.session)
            interval_minutes = int(effective.get("email_queue_interval_minutes") or DEFAULT_INTERVAL_MINUTES)
            batch_size = int(effective.get("email_queue_batch_size") or DEFAULT_BATCH_SIZE)
        except Exception as e:
            logger.warning(f"Could not read DB-saved email queue settings, using config.py/.env: {e}")

        scheduler.add_job(
            func=EmailQueueSchedulerService.drain_queue_task,
            args=[app, batch_size],
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="email_queue_drain_task",
            name=f"Send up to {batch_size} queued emails every {interval_minutes} minute(s)",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f"Email send queue scheduled: up to {batch_size} emails every {interval_minutes} minute(s)")

    @staticmethod
    def reschedule(app, batch_size: int, interval_minutes: int) -> None:
        """
        Applies a new batch size / interval to the already-running job, live —
        called from Settings → Email Queue when an admin saves new values.
        Without this, EMAIL_QUEUE_BATCH_SIZE/INTERVAL_MINUTES could only ever be
        changed by editing .env and restarting the server.
        """
        scheduler = BatchSchedulerService.scheduler
        if scheduler is None:
            raise RuntimeError("BatchSchedulerService.init_scheduler() must run before EmailQueueSchedulerService")

        scheduler.reschedule_job("email_queue_drain_task", trigger=IntervalTrigger(minutes=interval_minutes))
        scheduler.modify_job(
            "email_queue_drain_task",
            args=[app, batch_size],
            name=f"Send up to {batch_size} queued emails every {interval_minutes} minute(s)",
        )
        logger.info(f"Email send queue rescheduled: up to {batch_size} emails every {interval_minutes} minute(s)")

    @staticmethod
    def drain_queue_task(app, batch_size=DEFAULT_BATCH_SIZE):
        with app.app_context():
            from sqlalchemy import select
            from app.database.database import db
            from app.Investments.model import PendingEmail
            from app.Investments.route import _send_pending_email_now

            # Atomically claim rows (SELECT-then-send with no claim step would let a
            # second scheduler instance — e.g. a leftover duplicate server process —
            # grab the same 'Queued' rows and send them a second time. A single
            # UPDATE ... WHERE status = 'Queued' ... RETURNING id is what makes this
            # safe: Postgres row-locks each matched row for the duration of the
            # UPDATE, so a concurrent claim attempt on the same row simply finds it
            # no longer 'Queued' once it can proceed, and skips it.
            subq = (
                select(PendingEmail.id)
                .where(PendingEmail.status == "Queued")
                .order_by(PendingEmail.queued_at.asc().nullsfirst())
                .limit(batch_size)
            )
            claim_stmt = (
                PendingEmail.__table__.update()
                .where(PendingEmail.id.in_(subq))
                .values(status="Sending")
                .returning(PendingEmail.id)
            )
            queued_ids = [row[0] for row in db.session.execute(claim_stmt)]
            db.session.commit()
            if not queued_ids:
                return {"sent": 0, "failed": 0}

            sent, failed = 0, 0
            for email_id in queued_ids:
                try:
                    ok, message, _status = _send_pending_email_now(email_id)
                    if ok:
                        sent += 1
                    else:
                        failed += 1
                        logger.warning(f"Queued email {email_id} failed to send: {message}")
                except Exception as e:
                    failed += 1
                    logger.error(f"Queued email {email_id} raised while sending: {e}", exc_info=True)
                    # _send_pending_email_now normally always resolves the row to
                    # Confirmed/Failed itself, even on a caught SMTP error — this is
                    # only a backstop for something raising before it got that far,
                    # so the row can't get stuck in the transient 'Sending' state
                    # (invisible in both the Inbox and Processed tabs) forever.
                    try:
                        from app.database.database import db as _db
                        from app.Investments.model import PendingEmail as _PendingEmail
                        stuck = _db.session.get(_PendingEmail, email_id)
                        if stuck and stuck.status == "Sending":
                            stuck.status = "Failed"
                            _db.session.commit()
                    except Exception:
                        logger.error(f"Could not revert stuck 'Sending' status for email {email_id}", exc_info=True)

            logger.info(f"Email send queue: {sent} sent, {failed} failed this run")
            return {"sent": sent, "failed": failed}

    @staticmethod
    def get_status():
        """
        Next scheduled run time, how many are currently waiting, and the
        active drain rate (batch_size/interval_minutes) — for a status UI,
        and for estimating how long a bulk confirm will actually take to
        send (not just to queue). Deliberately NOT superadmin-gated like
        /settings/email-queue's PATCH is — reading the current rate is safe
        for anyone who can already see queued_count on this same response.
        """
        from app.database.database import db
        from app.Investments.model import PendingEmail
        from flask import current_app

        scheduler = BatchSchedulerService.scheduler
        next_run = None
        if scheduler is not None:
            job = scheduler.get_job("email_queue_drain_task")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        queued_count = db.session.query(PendingEmail).filter(PendingEmail.status == "Queued").count()

        batch_size = DEFAULT_BATCH_SIZE
        interval_minutes = DEFAULT_INTERVAL_MINUTES
        try:
            from app.Settings.service import get_effective_email_settings
            effective = get_effective_email_settings(current_app, db.session)
            batch_size = int(effective.get("email_queue_batch_size") or DEFAULT_BATCH_SIZE)
            interval_minutes = int(effective.get("email_queue_interval_minutes") or DEFAULT_INTERVAL_MINUTES)
        except Exception:
            pass

        return {
            "next_run_at": next_run,
            "queued_count": queued_count,
            "batch_size": batch_size,
            "interval_minutes": interval_minutes,
        }
