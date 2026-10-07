"""
Batch Management Service - Unit Tests

Test cases for automatic batch creation and closure functionality.
Run with: pytest tests/test_batch_management.py
"""

import pytest
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

from app.database.database import db
from app.logic.batch_management_service import BatchManagementService
from app.logic.batch_scheduler_service import BatchSchedulerService
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment


class TestBatchManagementService:
    """Test cases for BatchManagementService."""

    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Set up test database and fixtures."""
        with app.app_context():
            db.create_all()
            yield
            db.session.remove()
            db.drop_all()

    def test_next_thursday_morning_calculation(self, app):
        """Test calculation of next Thursday 9:00 AM EAT."""
        with app.app_context():
            thursday_morning = BatchManagementService._next_thursday_morning_eat()
            
            # Should be Thursday (weekday 3)
            assert thursday_morning.weekday() == 3
            
            # Should be 9:00 AM
            assert thursday_morning.hour == 9
            assert thursday_morning.minute == 0

    def test_next_thursday_date(self, app):
        """Test next Thursday date extraction."""
        with app.app_context():
            thursday_date = BatchManagementService._next_thursday_date()
            
            # Should be a date object
            assert isinstance(thursday_date, date)
            
            # Should be Thursday
            thursday_datetime = datetime.combine(thursday_date, datetime.min.time())
            assert thursday_datetime.weekday() == 3

    def test_batch_naming_convention(self, app):
        """Test batch naming follows convention."""
        with app.app_context():
            # Create fund and share class
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add_all([fund, share_class])
            db.session.commit()
            
            # Create batch
            batch = BatchManagementService.find_or_create_batch(share_class.id)
            
            # Batch name should follow pattern: AXIOM_CI-KES_YYYY-MM-DD
            assert batch.batch_name.startswith("AXIOM_CI-KES_")
            parts = batch.batch_name.split("_")
            assert len(parts) == 3
            assert parts[0] == "AXIOM"
            assert parts[1] == "CI-KES"
            # Check date format
            date.fromisoformat(parts[2])

    def test_find_existing_open_batch(self, app):
        """Test finding existing open batch."""
        with app.app_context():
            # Create fund and share class
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add_all([fund, share_class])
            db.session.commit()
            
            # First call should create batch
            batch1 = BatchManagementService.find_or_create_batch(share_class.id)
            assert batch1.is_open == True
            
            # Second call should return same batch
            batch2 = BatchManagementService.find_or_create_batch(share_class.id)
            assert batch2.id == batch1.id
            assert batch2.batch_name == batch1.batch_name

    def test_find_existing_open_batch_even_if_auto_close_passed(self, app):
        """Test that an open batch is reused even if auto_close_at has already passed."""
        with app.app_context():
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add_all([fund, share_class])
            db.session.commit()

            old_batch = Batch(
                batch_name="AXIOM_CI-KES_2026-04-10",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.session.add(old_batch)
            db.session.commit()

            batch = BatchManagementService.find_or_create_batch(share_class.id)
            assert batch.id == old_batch.id
            assert batch.is_open is True

    def test_create_batch_with_auto_close_at(self, app):
        """Test batch creation sets auto_close_at correctly."""
        with app.app_context():
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add_all([fund, share_class])
            db.session.commit()
            
            batch = BatchManagementService.find_or_create_batch(share_class.id)
            
            # auto_close_at should be set to Thursday 9 AM UTC
            assert batch.auto_close_at is not None
            assert batch.auto_close_at > datetime.now(timezone.utc)
            
            # Should be within 7 days (next Thursday)
            days_until_close = (batch.auto_close_at - datetime.now(timezone.utc)).days
            assert 1 <= days_until_close <= 7

    def test_share_class_constraint(self, app):
        """Test that batch enforces single share class constraint."""
        with app.app_context():
            # Create fund and two share classes
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class_kes = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            share_class_usd = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - USD",
                class_code="CI-USD",
                currency="USD",
            )
            db.session.add_all([fund, share_class_kes, share_class_usd])
            db.session.commit()
            
            # Create batch for KES
            batch = BatchManagementService.find_or_create_batch(share_class_kes.id)
            
            # Create investment for USD
            investment_usd = Investment(
                investor_name="Test User",
                investor_email="test@example.com",
                internal_client_code="TEST001",
                amount_deposited=Decimal("100000.00"),
                share_class_id=share_class_usd.id,
            )
            
            # Should raise error - share class mismatch
            with pytest.raises(ValueError):
                BatchManagementService.add_investor_to_batch(investment_usd, batch)

    def test_add_investor_to_batch(self, app):
        """Test adding investor to batch."""
        with app.app_context():
            # Create fund and share class
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add_all([fund, share_class])
            db.session.commit()
            
            # Create batch
            batch = BatchManagementService.find_or_create_batch(share_class.id)
            
            # Create investment
            investment = Investment(
                investor_name="Joy Kendi",
                investor_email="joy@example.com",
                internal_client_code="JOYK001",
                amount_deposited=Decimal("1000000.00"),
                share_class_id=share_class.id,
            )
            
            # Add to batch
            investment = BatchManagementService.add_investor_to_batch(investment, batch)
            
            assert investment.batch_id == batch.id
            
            # Verify in database
            fetched = Investment.query.get(investment.id)
            assert fetched.batch_id == batch.id

    def test_create_and_assign_investor(self, app):
        """Test complete workflow: create and assign investor."""
        with app.app_context():
            # Create fund and share class
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add_all([fund, share_class])
            db.session.commit()
            
            # Create investment
            investment = Investment(
                investor_name="Joy Kendi",
                investor_email="joy@example.com",
                internal_client_code="JOYK001",
                amount_deposited=Decimal("1000000.00"),
                share_class_id=share_class.id,
            )
            
            # Use complete workflow
            investment, batch = BatchManagementService.create_and_assign_investor_to_batch(
                investment=investment,
                share_class_id=share_class.id,
            )
            
            assert investment.batch_id == batch.id
            assert investment.share_class_id == batch.share_class_id
            assert batch.is_open == True

    def test_batch_closure(self, app):
        """Test batch closure (closing batch)."""
        with app.app_context():
            # Create batch
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            batch = Batch(
                batch_name="AXIOM_CI-KES_2026-04-10",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc),
            )
            db.session.add_all([fund, share_class, batch])
            db.session.commit()
            
            # Close batch
            result = BatchManagementService.close_batch(batch)
            assert result == True
            assert batch.is_open == False
            
            # Try closing again
            result = BatchManagementService.close_batch(batch)
            assert result == False  # Already closed

    def test_delete_empty_batch(self, app):
        """Test deleting empty batch."""
        with app.app_context():
            # Create empty batch
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            batch = Batch(
                batch_name="AXIOM_CI-KES_2026-04-10",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc),
            )
            db.session.add_all([fund, share_class, batch])
            db.session.commit()
            
            batch_id = batch.id
            
            # Delete empty batch
            result = BatchManagementService.delete_empty_batch(batch)
            assert result == True
            
            # Verify deleted
            assert Batch.query.get(batch_id) is None

    def test_cannot_delete_batch_with_investors(self, app):
        """Test that batches with investors cannot be deleted."""
        with app.app_context():
            # Create batch with investor
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            batch = Batch(
                batch_name="AXIOM_CI-KES_2026-04-10",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc),
            )
            investment = Investment(
                investor_name="Joy Kendi",
                investor_email="joy@example.com",
                internal_client_code="JOYK001",
                amount_deposited=Decimal("1000000.00"),
                batch_id=None,  # Will be set when added
                share_class_id=share_class.id,
            )
            db.session.add_all([fund, share_class, batch, investment])
            db.session.flush()
            
            investment.batch_id = batch.id
            db.session.commit()
            
            # Try to delete non-empty batch
            result = BatchManagementService.delete_empty_batch(batch)
            assert result == False  # Cannot delete
            
            # Batch should still exist
            assert Batch.query.get(batch.id) is not None

    def test_get_batches_ready_for_closure(self, app):
        """Test querying batches ready for closure."""
        with app.app_context():
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            
            # Create batch with past auto_close_at
            batch_past = Batch(
                batch_name="AXIOM_CI-KES_2026-04-10",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            
            # Create batch with future auto_close_at
            batch_future = Batch(
                batch_name="AXIOM_CI-KES_2026-04-18",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            
            db.session.add_all([fund, share_class, batch_past, batch_future])
            db.session.commit()
            
            # Get batches ready for closure
            ready = BatchManagementService.get_batches_ready_for_closure()
            
            # Should only return past batch
            assert len(ready) >= 1
            assert batch_past.id in [b.id for b in ready]

    def test_process_batch_closures(self, app):
        """Test processing batch closures."""
        with app.app_context():
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            
            # Create empty batch (should be deleted)
            batch_empty = Batch(
                batch_name="AXIOM_CI-KES_2026-04-10",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            
            db.session.add_all([fund, share_class, batch_empty])
            db.session.commit()
            
            # Process closures
            stats = BatchManagementService.process_batch_closures()
            
            assert stats["total"] >= 1
            assert stats["deleted"] >= 1  # Empty batch was deleted

    def test_get_batch_statistics(self, app):
        """Test getting batch statistics."""
        with app.app_context():
            fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
            db.session.add(fund)
            db.session.flush()  # Ensure fund.id is set
            share_class = ShareClass(
                core_fund_id=fund.id,
                class_name="Class I - KES",
                class_code="CI-KES",
                currency="KES",
            )
            db.session.add(share_class)
            db.session.flush()  # Ensure share_class.id is set
            batch = Batch(
                batch_name="AXIOM_CI-KES_2026-04-18",
                share_class_id=share_class.id,
                is_open=True,
                auto_close_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch.id is set
            
            # Add investors
            investment1 = Investment(
                investor_name="Joy Kendi",
                investor_email="joy@example.com",
                internal_client_code="JOYK001",
                amount_deposited=Decimal("1000000.00"),
                batch_id=batch.id,
                share_class_id=share_class.id,
            )
            investment2 = Investment(
                investor_name="John Doe",
                investor_email="john@example.com",
                internal_client_code="JOHND001",
                amount_deposited=Decimal("500000.00"),
                batch_id=batch.id,
                share_class_id=share_class.id,
            )
            
            db.session.add_all([investment1, investment2])
            db.session.commit()
            
            # Get statistics
            stats = BatchManagementService.get_batch_statistics(batch.id)
            
            assert stats["batch_name"] == "AXIOM_CI-KES_2026-04-18"
            assert stats["investor_count"] == 2
            assert stats["total_principal"] == 1500000.00


class TestBatchSchedulerService:
    """Test cases for BatchSchedulerService."""

    def test_get_scheduler_status_not_initialized(self):
        """Test getting scheduler status when not initialized."""
        # Reset scheduler
        original_scheduler = BatchSchedulerService.scheduler
        BatchSchedulerService.scheduler = None
        
        status = BatchSchedulerService.get_scheduler_status()
        assert status["status"] == "not_initialized"
        
        # Restore
        BatchSchedulerService.scheduler = original_scheduler

    def test_init_scheduler(self, app):
        """Test scheduler initialization."""
        with app.app_context():
            try:
                scheduler = BatchSchedulerService.init_scheduler(app)
                assert scheduler is not None
                assert scheduler.running == True
                
                # Check batch closure job
                jobs = scheduler.get_jobs()
                assert any(job.id == "batch_closure_task" for job in jobs)
                
                BatchSchedulerService.shutdown_scheduler()
            except Exception as e:
                # APScheduler may not be installed
                pytest.skip(f"APScheduler not available: {str(e)}")
