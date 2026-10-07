"""
Batch Scheduler Service - Scheduled Tasks for Batch Closure

Handles:
- Scheduled execution of batch closure processing
- Excel export generation before closure
- Integration with APScheduler for autonomous task scheduling
"""

import logging
from datetime import datetime, time, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.logic.batch_management_service import BatchManagementService

logger = logging.getLogger(__name__)

# EAT (East Africa Time) is UTC+3
# When it's 9:00 AM in EAT, it's 6:00 AM in UTC
BATCH_CLOSURE_HOUR_UTC = 6
BATCH_CLOSURE_MINUTE_UTC = 0
BATCH_CLOSURE_WEEKDAY = 3  # Thursday (0=Monday, 1=Tuesday, ..., 3=Thursday, ..., 6=Sunday)


class BatchSchedulerService:
    """
    Service for scheduling autonomous batch closure tasks.
    
    Runs at Thursday 6:00 AM UTC (= Thursday 9:00 AM EAT).
    """

    scheduler: BackgroundScheduler = None

    @staticmethod
    def init_scheduler(app) -> BackgroundScheduler:
        """
        Initialize the APScheduler scheduler.
        
        Should be called during Flask app initialization.
        
        Args:
            app: Flask app instance
        
        Returns:
            BackgroundScheduler instance
        """
        if BatchSchedulerService.scheduler is not None:
            logger.warning("Scheduler already initialized")
            return BatchSchedulerService.scheduler

        try:
            scheduler = BackgroundScheduler()
            
            # Add batch closure job
            # Run every Thursday at 6:00 AM UTC (9:00 AM EAT)
            scheduler.add_job(
                func=BatchSchedulerService.process_batch_closures_task,
                trigger=CronTrigger(
                    day_of_week=BATCH_CLOSURE_WEEKDAY,
                    hour=BATCH_CLOSURE_HOUR_UTC,
                    minute=BATCH_CLOSURE_MINUTE_UTC,
                    timezone="UTC"
                ),
                id="batch_closure_task",
                name="Process batch closures at Thursday 9 AM EAT",
                replace_existing=True,
                coalesce=True,  # Coalesce multiple triggers into one
                max_instances=1,  # Only one instance at a time
            )

            scheduler.start()
            logger.info("Batch scheduler initialized and started")
            
            BatchSchedulerService.scheduler = scheduler
            return scheduler

        except Exception as e:
            logger.error(f"Failed to initialize batch scheduler: {str(e)}")
            raise

    @staticmethod
    def shutdown_scheduler():
        """Shut down the scheduler gracefully."""
        if BatchSchedulerService.scheduler is not None:
            try:
                BatchSchedulerService.scheduler.shutdown(wait=True)
                logger.info("Batch scheduler shut down")
                BatchSchedulerService.scheduler = None
            except Exception as e:
                logger.error(f"Error shutting down scheduler: {str(e)}")

    @staticmethod
    def process_batch_closures_task():
        """
        Autonomous task executed at Thursday 9:00 AM EAT.
        
        Processes all batches ready for closure:
        1. Delete empty batches
        2. Close batches with investors (set is_open=False)
        3. Generate Excel exports for closed batches (future)
        """
        try:
            logger.info("Starting batch closure processing task...")

            # Process closures
            stats = BatchManagementService.process_batch_closures()

            logger.info(
                f"Batch closure task completed: "
                f"closed={stats['closed']}, "
                f"deleted={stats['deleted']}, "
                f"errors={len(stats['errors'])}"
            )

            # Log any errors
            if stats["errors"]:
                for error in stats["errors"]:
                    logger.error(f"  - {error}")

            return stats

        except Exception as e:
            logger.error(f"Error in batch closure task: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_scheduler_status() -> dict:
        """
        Get current scheduler status.
        
        Returns:
            dict with scheduler info and next run time
        """
        if BatchSchedulerService.scheduler is None:
            return {"status": "not_initialized"}

        try:
            jobs = BatchSchedulerService.scheduler.get_jobs()
            batch_closure_job = None

            for job in jobs:
                if job.id == "batch_closure_task":
                    batch_closure_job = job
                    break

            if batch_closure_job is None:
                return {"status": "initialized", "batch_closure_job": "not_found"}

            return {
                "status": "running" if BatchSchedulerService.scheduler.running else "stopped",
                "batch_closure_job": {
                    "id": batch_closure_job.id,
                    "name": batch_closure_job.name,
                    "trigger": str(batch_closure_job.trigger),
                    "next_run_time": batch_closure_job.next_run_time.isoformat() if batch_closure_job.next_run_time else None,
                },
            }

        except Exception as e:
            logger.error(f"Error getting scheduler status: {str(e)}")
            return {"status": "error", "error": str(e)}

    @staticmethod
    def trigger_batch_closures_manually() -> dict:
        """
        Manually trigger batch closure processing (for testing/admin).
        
        Returns:
            dict with closure statistics
        """
        logger.info("Manual batch closure triggered")
        return BatchSchedulerService.process_batch_closures_task()
