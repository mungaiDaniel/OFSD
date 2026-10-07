"""
Integration Examples for Batch Management Service

This module shows how to integrate the batch management service
into existing routes and Flask app initialization.
"""

# ============================================================================
# EXAMPLE 1: Integrating into Investors Route (POST /api/v1/investors)
# ============================================================================

"""
In your investors route handler (e.g., app/Investments/route.py):

from flask import request, jsonify
from app.logic.batch_management_service import BatchManagementService
from app.Investments.model import Investment
from app.database.database import db

@investors_bp.route('/api/v1/investors', methods=['POST'])
@jwt_required()
def create_investor():
    data = request.get_json()
    
    try:
        # Validate input
        if not data.get('share_class_id'):
            return {"error": "share_class_id is required"}, 400
        
        # Create investment record
        investment = Investment(
            investor_name=data['investor_name'],
            investor_email=data['investor_email'],
            investor_phone=data.get('investor_phone'),
            internal_client_code=data['internal_client_code'],
            amount_deposited=data['amount_deposited'],
            fund_id=data.get('fund_id'),
            share_class_id=data['share_class_id'],
            deposit_date=parse_date(data.get('deposit_date')),
            wealth_manager=data.get('wealth_manager'),
            IFA=data.get('IFA'),
        )
        
        # Use batch management service to find/create batch and assign investor
        investment, batch = BatchManagementService.create_and_assign_investor_to_batch(
            investment=investment,
            share_class_id=data['share_class_id'],
        )
        
        return {
            "investor_id": investment.id,
            "batch_id": batch.id,
            "batch_name": batch.batch_name,
            "message": "Investor created and assigned to batch",
        }, 201
        
    except ValueError as e:
        return {"error": str(e)}, 400
    except Exception as e:
        logger.error(f"Error creating investor: {str(e)}")
        return {"error": "Internal server error"}, 500
"""


# ============================================================================
# EXAMPLE 2: Initializing Scheduler in Flask App
# ============================================================================

"""
In your Flask app factory (e.g., create_app() or __init__.py):

from flask import Flask
from app.logic.batch_scheduler_service import BatchSchedulerService

def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(load_config(config_name))
    
    # ... other initializations ...
    
    # Initialize the batch scheduler
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            BatchSchedulerService.init_scheduler(app)
        except Exception as e:
            app.logger.error(f"Failed to initialize batch scheduler: {str(e)}")
            # Don't fail app startup if scheduler fails
    
    # Register shutdown handler
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        BatchSchedulerService.shutdown_scheduler()
    
    return app
"""


# ============================================================================
# EXAMPLE 3: Admin Endpoint to View Scheduler Status
# ============================================================================

"""
Add this to your admin/monitoring route file:

from flask import Blueprint, jsonify
from app.logic.batch_scheduler_service import BatchSchedulerService

admin_bp = Blueprint('admin', __name__, url_prefix='/api/v1/admin')

@admin_bp.route('/batch-scheduler/status', methods=['GET'])
@jwt_required()
@require_admin
def get_batch_scheduler_status():
    '''Get current batch scheduler status.'''
    status = BatchSchedulerService.get_scheduler_status()
    return status, 200


@admin_bp.route('/batch-scheduler/trigger-closures', methods=['POST'])
@jwt_required()
@require_admin
def trigger_batch_closures():
    '''Manually trigger batch closure processing (for testing).'''
    stats = BatchSchedulerService.trigger_batch_closures_manually()
    return stats, 200
"""


# ============================================================================
# EXAMPLE 4: Testing Batch Management Service
# ============================================================================

"""
Unit test examples:

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from app.logic.batch_management_service import BatchManagementService
from app.Batch.core_fund import CoreFund
from app.Funds import ShareClass, InvestorShares
from app.Investments.model import Investment
from app.Batch.model import Batch

def test_next_thursday_morning():
    '''Test Thursday calculation.'''
    # Test on a Monday
    thursday_morning = BatchManagementService._next_thursday_morning_eat()
    assert thursday_morning.weekday() == 3  # Thursday
    assert thursday_morning.hour == 9
    assert thursday_morning.minute == 0

def test_find_existing_open_batch(app, db):
    '''Test finding existing open batch.'''
    with app.app_context():
        # Create fund and share class
        fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
        share_class = ShareClass(
            core_fund_id=fund.id,
            class_name="Class I - KES",
            class_code="CI-KES",
            currency="KES"
        )
        db.session.add_all([fund, share_class])
        db.session.flush()
        
        # Find or create batch (should create)
        batch1 = BatchManagementService.find_or_create_batch(share_class.id)
        assert batch1.is_open == True
        
        # Find or create batch again (should return same)
        batch2 = BatchManagementService.find_or_create_batch(share_class.id)
        assert batch2.id == batch1.id

def test_batch_naming_convention(app, db):
    '''Test batch naming follows convention.'''
    with app.app_context():
        fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
        share_class = ShareClass(
            core_fund_id=fund.id,
            class_name="Class I - KES",
            class_code="CI-KES",
            currency="KES"
        )
        db.session.add_all([fund, share_class])
        db.session.flush()
        
        batch = BatchManagementService.find_or_create_batch(share_class.id)
        # Should follow pattern: AXIOM_CI-KES_YYYY-MM-DD
        assert batch.batch_name.startswith("AXIOM_CI-KES_")

def test_investor_to_batch_assignment(app, db):
    '''Test adding investor to batch.'''
    with app.app_context():
        # Create fund, share class, batch
        fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
        share_class = ShareClass(
            core_fund_id=fund.id,
            class_name="Class I - KES",
            class_code="CI-KES",
            currency="KES"
        )
        db.session.add_all([fund, share_class])
        db.session.flush()
        
        batch = BatchManagementService.find_or_create_batch(share_class.id)
        
        # Create and assign investor
        investment = Investment(
            investor_name="Joy Kendi",
            investor_email="joy@example.com",
            internal_client_code="JOYK001",
            amount_deposited=Decimal("1000000.00"),
            share_class_id=share_class.id,
        )
        
        investment, assigned_batch = BatchManagementService.create_and_assign_investor_to_batch(
            investment=investment,
            share_class_id=share_class.id,
        )
        
        assert investment.batch_id == batch.id
        assert assigned_batch.id == batch.id

def test_batch_closure_processing(app, db):
    '''Test batch closure at auto_close_at time.'''
    with app.app_context():
        # Create batch with past auto_close_at
        fund = CoreFund(fund_name="Axiom", fund_code="AXIOM")
        share_class = ShareClass(
            core_fund_id=fund.id,
            class_name="Class I - KES",
            class_code="CI-KES",
            currency="KES"
        )
        db.session.add_all([fund, share_class])
        db.session.flush()
        
        batch = Batch(
            batch_name="AXIOM_CI-KES_2026-04-10",
            share_class_id=share_class.id,
            is_open=True,
            auto_close_at=datetime.now(timezone.utc),
        )
        db.session.add(batch)
        db.session.commit()
        
        # Process closures
        stats = BatchManagementService.process_batch_closures()
        
        # Batch should be closed (no investors)
        assert stats["deleted"] >= 1
"""


# ============================================================================
# EXAMPLE 5: Batch Management Query Helpers
# ============================================================================

"""
Useful query helpers for batch management:

from app.logic.batch_management_service import BatchManagementService
from app.Batch.model import Batch
from app.Investments.model import Investment

# Get all open batches for a share class
open_batches = BatchManagementService.get_open_batches_for_share_class(share_class_id=1)
for batch in open_batches:
    print(f"{batch.batch_name}: closes at {batch.auto_close_at}")

# Get batch statistics
stats = BatchManagementService.get_batch_statistics(batch_id=1)
print(f"Batch: {stats['batch_name']}")
print(f"Investors: {stats['investor_count']}")
print(f"Total Principal: ${stats['total_principal']:,.2f}")

# Get batches ready for closure
ready_to_close = BatchManagementService.get_batches_ready_for_closure()
print(f"Batches ready for closure: {len(ready_to_close)}")

# Manual batch closure (for admin)
batch = Batch.query.get(batch_id)
BatchManagementService.close_batch(batch, reason="Manual admin closure")
"""
