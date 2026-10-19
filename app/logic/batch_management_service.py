"""
Batch Management Service - Automatic Batch Creation and Lifecycle Management

Handles:
- Finding or creating open batches for new investors
- Auto-batch naming conventions
- Timezone-aware auto-close scheduling (Thursday 9:00 AM EAT)
- Batch closure and cleanup
"""

from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
import logging
from typing import Optional, Tuple

from sqlalchemy import and_, or_

from app.database.database import db
from app.database.product_type import SHARES
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment

logger = logging.getLogger(__name__)

# EAT (East Africa Time) is UTC+3
EAT_TIMEZONE_OFFSET = timedelta(hours=3)


class BatchManagementService:
    """
    Service for automatic batch management.
    
    Key Constraint:
    - A batch belongs to exactly ONE share class
    - Investors in different share classes cannot share a batch
    """

    @staticmethod
    def _get_eat_now() -> datetime:
        """Get current time in EAT (UTC+3)."""
        return datetime.now(timezone.utc) + EAT_TIMEZONE_OFFSET

    @staticmethod
    def _next_thursday_morning_eat() -> datetime:
        """
        Calculate next Thursday 9:00 AM EAT.
        
        Returns:
            datetime in EAT timezone (UTC+3)
        """
        now_eat = BatchManagementService._get_eat_now()
        
        # Days of week: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
        current_weekday = now_eat.weekday()
        
        # Calculate days until next Thursday (3)
        days_until_thursday = (3 - current_weekday) % 7
        
        # If it's already Thursday and before 9 AM, use today
        if days_until_thursday == 0 and now_eat.hour < 9:
            next_thursday = now_eat.date()
        else:
            # If it's Thursday but after 9 AM, or any other day, move to next Thursday
            if days_until_thursday == 0:
                days_until_thursday = 7
            next_thursday = (now_eat.date()) + timedelta(days=days_until_thursday)
        
        # Set to 9:00 AM EAT - convert date to datetime
        thursday_9am_eat = datetime.combine(next_thursday, datetime.min.time()).replace(hour=9, minute=0, second=0, microsecond=0)
        
        return thursday_9am_eat

    @staticmethod
    def _next_thursday_date() -> date:
        """Get next Thursday's date."""
        thursday_eat = BatchManagementService._next_thursday_morning_eat()
        return thursday_eat.date()

    @staticmethod
    def find_or_create_batch(
        share_class_id: int,
        core_fund_id: Optional[int] = None,
        batch_name_date: Optional[date] = None,
    ) -> Batch:
        """
        Find an open batch for a share class, or create one.
        
        Algorithm:
        1. Look for open batches with matching share_class_id and auto_close_at > now()
        2. If found: return the first one
        3. If not found: create new batch with auto-generated name (date comes from
           `batch_name_date` when provided, otherwise defaults to today in EAT)
        
        Args:
            share_class_id: ID of the share class
            core_fund_id: Optional, for looking up fund_code if share class not loaded
            batch_name_date: Optional date to embed into the batch_name (deposit date)
        
        Returns:
            Batch instance (either existing or newly created)
        
        Raises:
            ValueError: If share class not found
        """
        # Load share class
        share_class = ShareClass.query.get(share_class_id)
        if not share_class:
            raise ValueError(f"Share class {share_class_id} not found")

        now = datetime.now(timezone.utc)

        # Look for an existing open batch with this share class.
        # Reuse an open batch whenever the batch is still marked open.
        existing_batch = (
            Batch.query.filter(
                Batch.share_class_id == share_class_id,
                Batch.is_open == True,
                # Never reuse a deployed/active batch
                Batch.deployment_confirmed != True,
                Batch.stage < 3,
                Batch.is_active != True,
            )
            .order_by(Batch.date_created.asc())
            .first()
        )

        if existing_batch:
            logger.info(f"Found existing open batch: {existing_batch.batch_name} (ID: {existing_batch.id})")
            return existing_batch

        # Create new batch
        new_batch = BatchManagementService._create_new_batch(share_class, batch_name_date=batch_name_date)
        logger.info(f"Created new batch: {new_batch.batch_name} (ID: {new_batch.id})")
        return new_batch

    @staticmethod
    def _create_new_batch(share_class: ShareClass, batch_name_date: Optional[date] = None) -> Batch:
        """
        Create a new auto-batch with naming convention.
        
        Naming: {fund_code}_{class_code}_{deposit_date}
        Example: AXIOM_CI-KES_2026-04-18
        
        Args:
            share_class: ShareClass instance
        
        Returns:
            New Batch instance (committed to database)
        """
        # Get core fund
        core_fund = CoreFund.query.get(share_class.core_fund_id)
        if not core_fund:
            raise ValueError(f"Core fund {share_class.core_fund_id} not found")

        # Generate batch name using deposit date (not the Thursday close date).
        # If no deposit date is provided, default to "today" in EAT for consistency.
        name_date = batch_name_date
        if not name_date:
            name_date = BatchManagementService._get_eat_now().date()
        base_batch_name = f"{core_fund.fund_code}_{share_class.class_code}_{name_date}"

        # `batches.batch_name` is globally unique.
        # If a batch with the same canonical name already exists (e.g. prior closed batch
        # on the same date), generate a deterministic suffixed name.
        batch_name = base_batch_name
        suffix = 2
        while Batch.query.filter(Batch.batch_name == batch_name).first() is not None:
            batch_name = f"{base_batch_name}_{suffix}"
            suffix += 1

        # DPRP does not follow the normal recurring weekly-batch cycle: it runs
        # as a SINGLE persistent batch that accumulates every deposit until one
        # deployment event (that's the actual mechanism behind its
        # oversubscription/pro-rata handling — one fixed pool of shares being
        # competed for, not a new independent pool every week). Explicitly flag
        # this here rather than assume the normal scheduler already handles a
        # non-recurring fund correctly: giving it no auto_close_at means
        # get_batches_ready_for_closure()'s `auto_close_at <= now()` filter
        # never matches it (NULL <= anything is NULL/false in SQL), so
        # find_or_create_batch() keeps reusing this same open batch for every
        # subsequent DPRP deposit instead of the usual "reuse until Thursday,
        # then spin up a new one" behavior every other fund gets.
        # Task 8: product is the real CoreFund.product_type column now, not a
        # name/code guess — SHARES currently only ever means DPRP, so this is
        # still exactly the "is this the single-persistent-batch IPO-style
        # fund" signal, just driven by the authoritative column.
        if core_fund.product_type == SHARES:
            auto_close_at = None
        else:
            # Calculate auto_close_at (next Thursday 9:00 AM UTC)
            thursday_9am_eat = BatchManagementService._next_thursday_morning_eat()
            # Convert back to UTC for storage
            thursday_9am_utc = thursday_9am_eat - EAT_TIMEZONE_OFFSET
            auto_close_at = thursday_9am_utc.replace(tzinfo=timezone.utc)

        # Create batch — product_type is intentionally omitted here: Batch's
        # own before_insert event (app/Batch/model.py) inherits and validates
        # it from share_class.product_type automatically, the same way
        # Investment.product_type inherits from its Batch.
        batch = Batch(
            batch_name=batch_name,
            share_class_id=share_class.id,
            is_open=True,
            auto_close_at=auto_close_at,
            date_deployed=None,  # Will be set during deployment
            is_active=False,  # Becomes active after deployment
            stage=1,  # Deposited stage
        )

        db.session.add(batch)
        db.session.commit()

        return batch

    @staticmethod
    def add_investor_to_batch(
        investment: Investment,
        batch: Batch,
    ) -> Investment:
        """
        Add an investor (Investment record) to a batch.
        
        Args:
            investment: Investment instance (not yet committed)
            batch: Batch instance
        
        Returns:
            Updated Investment instance (committed to database)
        
        Raises:
            ValueError: If investment's share_class_id doesn't match batch's
        """
        # Validate share class match
        if investment.share_class_id != batch.share_class_id:
            raise ValueError(
                f"Investment share class {investment.share_class_id} "
                f"does not match batch share class {batch.share_class_id}"
            )

        # Block mixing: a SHARES deposit cannot go into a FUNDS batch and vice
        # versa. The share_class_id check above already makes a real mismatch
        # unreachable through this path, but this keeps the rule explicit and
        # gives a clear error if that invariant is ever loosened.
        if investment.product_type and investment.product_type != batch.product_type:
            raise ValueError(
                f"Cannot add a {investment.product_type} deposit to a "
                f"{batch.product_type} batch ({batch.batch_name})"
            )
        investment.product_type = batch.product_type

        # Minimum deposit (before fees) for SHARES batches — see Task 2 /
        # app.logic.shares_transfer_service.get_min_deposit_usd.
        if batch.product_type == SHARES:
            from app.logic.shares_transfer_service import get_min_deposit_usd
            min_deposit = get_min_deposit_usd()
            if (
                Decimal(str(investment.amount_deposited or 0)) < min_deposit
                and not getattr(investment, "min_deposit_exception", False)
            ):
                raise ValueError(
                    f"Deposit of {investment.amount_deposited} USD is below the "
                    f"{min_deposit} USD minimum (before fees) for a SHARES batch"
                )

        investment.batch_id = batch.id
        db.session.add(investment)
        db.session.commit()

        logger.info(
            f"Added investor {investment.internal_client_code} "
            f"to batch {batch.batch_name} (ID: {batch.id})"
        )
        return investment

    @staticmethod
    def create_and_assign_investor_to_batch(
        investment: Investment,
        share_class_id: int,
    ) -> Tuple[Investment, Batch]:
        """
        Complete workflow: find/create batch and add investor.
        
        This is the main entry point for adding investors.
        
        Args:
            investment: Investment instance (should have share_class_id set)
            share_class_id: ID of the share class
        
        Returns:
            Tuple of (updated Investment, assigned Batch)
        
        Raises:
            ValueError: If validation fails
        """
        # Validate investment has share_class_id
        if not investment.share_class_id:
            investment.share_class_id = share_class_id
        elif investment.share_class_id != share_class_id:
            raise ValueError(
                f"Investment share class {investment.share_class_id} "
                f"does not match provided share class {share_class_id}"
            )

        # Find or create batch.
        # When creating a new batch, embed the investor's deposit date into the batch name.
        preferred_name_date = None
        try:
            if getattr(investment, "deposit_date", None):
                preferred_name_date = investment.deposit_date
            elif getattr(investment, "date_deposited", None):
                preferred_name_date = investment.date_deposited.date()
        except Exception:
            preferred_name_date = None

        batch = BatchManagementService.find_or_create_batch(
            share_class_id,
            batch_name_date=preferred_name_date,
        )

        # Add investor to batch
        investment = BatchManagementService.add_investor_to_batch(investment, batch)

        return investment, batch

    @staticmethod
    def close_batch(batch: Batch, reason: str = "Auto-closed") -> bool:
        """
        Close a batch (set is_open=False).
        
        Args:
            batch: Batch to close
            reason: Reason for closing
        
        Returns:
            True if successfully closed, False if already closed
        """
        if not batch.is_open:
            logger.warning(f"Batch {batch.batch_name} is already closed")
            return False

        batch.is_open = False
        db.session.commit()

        logger.info(f"Closed batch {batch.batch_name}: {reason}")
        return True

    @staticmethod
    def delete_empty_batch(batch: Batch) -> bool:
        """
        Delete a batch if it has no investors.
        
        Args:
            batch: Batch to potentially delete
        
        Returns:
            True if deleted, False if batch has investors
        """
        investor_count = Investment.query.filter_by(batch_id=batch.id).count()

        if investor_count > 0:
            logger.warning(
                f"Cannot delete batch {batch.batch_name}: "
                f"has {investor_count} investors"
            )
            return False

        batch_name = batch.batch_name
        batch_id = batch.id
        db.session.delete(batch)
        db.session.commit()

        logger.info(f"Deleted empty batch {batch_name} (ID: {batch_id})")
        return True

    @staticmethod
    def get_batches_ready_for_closure() -> list:
        """
        Find all batches that are ready to close.
        
        Criteria:
        - is_open = True
        - auto_close_at <= now() (in UTC)
        
        Returns:
            List of Batch instances
        """
        now = datetime.now(timezone.utc)

        batches = Batch.query.filter(
            Batch.is_open == True,
            Batch.auto_close_at <= now,
        ).all()

        return batches

    @staticmethod
    def process_batch_closures() -> dict:
        """
        Process all batches ready for closure.
        
        For each batch:
        1. If empty: delete it
        2. If has investors: close it (set is_open=False)
        
        Returns:
            dict with closure statistics
        """
        batches_to_close = BatchManagementService.get_batches_ready_for_closure()

        stats = {
            "total": len(batches_to_close),
            "deleted": 0,
            "closed": 0,
            "errors": [],
        }

        for batch in batches_to_close:
            try:
                # Try to delete empty batches
                if BatchManagementService.delete_empty_batch(batch):
                    stats["deleted"] += 1
                else:
                    # Close non-empty batches
                    if BatchManagementService.close_batch(batch, "Auto-closed at Thursday 9 AM EAT"):
                        stats["closed"] += 1
            except Exception as e:
                error_msg = f"Error processing batch {batch.batch_name}: {str(e)}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)

        logger.info(
            f"Batch closure processing: "
            f"closed={stats['closed']}, deleted={stats['deleted']}, errors={len(stats['errors'])}"
        )
        return stats

    @staticmethod
    def get_open_batches_for_share_class(share_class_id: int) -> list:
        """
        Get all open batches for a share class.
        
        Args:
            share_class_id: ID of the share class
        
        Returns:
            List of open Batch instances
        """
        return (
            Batch.query.filter(
                Batch.share_class_id == share_class_id,
                Batch.is_open == True,
            )
            .order_by(Batch.date_created.asc())
            .all()
        )

    @staticmethod
    def get_batch_statistics(batch_id: int) -> dict:
        """
        Get statistics for a batch.
        
        Args:
            batch_id: ID of the batch
        
        Returns:
            dict with batch info and investor counts
        """
        batch = Batch.query.get(batch_id)
        if not batch:
            return {"error": "Batch not found"}

        investor_count = Investment.query.filter_by(batch_id=batch_id).count()
        total_principal = (
            db.session.query(db.func.sum(Investment.amount_deposited))
            .filter_by(batch_id=batch_id)
            .scalar() or Decimal("0")
        )

        return {
            "batch_id": batch_id,
            "batch_name": batch.batch_name,
            "share_class_id": batch.share_class_id,
            "is_open": batch.is_open,
            "auto_close_at": batch.auto_close_at,
            "investor_count": investor_count,
            "total_principal": float(total_principal),
            "date_created": batch.date_created,
        }
