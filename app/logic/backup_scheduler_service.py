"""
Backup Scheduler Service - daily automatic database backup.

Adds a job to the same APScheduler instance BatchSchedulerService uses.
Only registered when app.config['DB_BACKUP_ENABLED'] is true (see config.py) —
off by default in every environment until Azure/OneDrive credentials are set.
"""
import logging

from apscheduler.triggers.cron import CronTrigger

from app.logic.batch_scheduler_service import BatchSchedulerService
from app.utils.backup_service import BackupService

logger = logging.getLogger(__name__)


class BackupSchedulerService:

    @staticmethod
    def init_scheduler(app) -> None:
        scheduler = BatchSchedulerService.scheduler
        if scheduler is None:
            raise RuntimeError("BatchSchedulerService.init_scheduler() must run before BackupSchedulerService")

        hour = app.config.get("DB_BACKUP_HOUR_UTC", 1)
        minute = app.config.get("DB_BACKUP_MINUTE_UTC", 0)

        scheduler.add_job(
            func=BackupSchedulerService.run_backup_task,
            args=[app],
            trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
            id="daily_db_backup_task",
            name=f"Daily DB backup at {hour:02d}:{minute:02d} UTC",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f"Daily DB backup scheduled for {hour:02d}:{minute:02d} UTC")

    @staticmethod
    def run_backup_task(app) -> None:
        with app.app_context():
            log = BackupService.run_database_backup(app, triggered_by="scheduled")
            if log.status != "success":
                logger.error(f"Scheduled backup failed: {log.error_message}")
