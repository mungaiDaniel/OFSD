import logging
from datetime import datetime, timezone
from app.utils.email_service import EmailService

logger = logging.getLogger(__name__)

class StatusUpdateController:
    """
    Dedicated controller for managing Batch progress tracker stages 
    and triggering asynchronous status-driven investor emails.
    """

    @classmethod
    def handle_status_transition(cls, batch, data, session):
        """
        Detects changes in batch fields and triggers appropriate stage-based side effects.
        
        Transitions:
        - Stage 2 (Transferred): is_transferred False -> True
        - Stage 3 (Active): date_deployed set OR deployment_confirmed True
        """
        old_is_transferred = batch.is_transferred
        old_is_active = batch.is_active or batch.deployment_confirmed

        # 1. Update fields from incoming data
        if 'is_transferred' in data:
            batch.is_transferred = bool(data['is_transferred'])
        
        if 'date_deployed' in data and data['date_deployed']:
            try:
                batch.date_deployed = datetime.fromisoformat(str(data['date_deployed']))
                # Deployment date implies confirmation and active status in this workflow
                batch.deployment_confirmed = True
                batch.is_active = True
            except ValueError:
                logger.warning(f"Invalid date format for batch {batch.id}: {data['date_deployed']}")

        if 'deployment_confirmed' in data:
            batch.deployment_confirmed = bool(data['deployment_confirmed'])
            if batch.deployment_confirmed:
                batch.is_active = True

        if 'is_active' in data:
            batch.is_active = bool(data['is_active'])

        # 2. Persist state
        session.commit()

        # 3. Trigger Stage-based Emails (Asynchronous)
        
        # Stage 2: Offshore Transfer
        if batch.is_transferred and not old_is_transferred:
            logger.info(f"Triggering Stage 2 Emails for Batch {batch.id}")
            EmailService.send_offshore_transfer_batch(batch, trigger_source="batch.update_status.stage_2_transfer")
            batch.stage = 2
            session.commit()

        # Stage 3: Investment Active
        new_is_active = batch.is_active or batch.deployment_confirmed
        if new_is_active and not old_is_active and batch.date_deployed is not None:
            logger.info(f"Triggering Stage 3 Emails for Batch {batch.id}")
            EmailService.send_investment_active_batch(batch, trigger_source="batch.update_status.stage_3_deploy")
            batch.stage = 3
            session.commit()

        return batch
