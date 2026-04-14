"""
Pytest Configuration & Fixtures
================================
Sets up test environment, database, and reusable test fixtures.

Run tests with:
    pytest
    pytest -v                  # verbose
    pytest --cov              # with coverage
    pytest tests/test_investments.py -v
"""

import pytest
import os
from datetime import datetime, timezone
from decimal import Decimal
from app.database.database import db
from config import TestingConfig
from main import create_app
from app.Batch.model import Batch
from app.Investments.model import Investment, Withdrawal
from app.Batch.fund_routes import CoreFund
from app.utils.audit_log import AuditLog


@pytest.fixture(scope='session')
def app():
    """
    Create application for the test session.
    Uses TestingConfig for isolated database.
    """
    app = create_app(config_filename=TestingConfig)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    return app


@pytest.fixture
def client(app):
    """
    Test client for making requests to the app.
    """
    return app.test_client()


@pytest.fixture
def runner(app):
    """
    Test runner for CLI commands.
    """
    return app.test_cli_runner()


@pytest.fixture(autouse=True)
def reset_db(app):
    """
    Reset database before each test.
    This fixture runs automatically for all tests.
    Ensures app context and fresh database for isolation.
    """
    with app.app_context():
        # Rollback any previous transactions
        db.session.rollback()
        # Drop all tables
        db.drop_all()
        # Recreate all tables from models
        db.create_all()
        yield
        # Cleanup after test
        db.session.rollback()
        db.session.remove()


@pytest.fixture
def auth_token(client):
    """
    Generate a valid JWT token for authenticated requests.
    Uses flask-jwt-extended to create a test token.
    """
    from flask_jwt_extended import create_access_token
    
    # Create a test user (or use a known user_email)
    test_user_identity = 'admin@example.com'
    return create_access_token(identity=test_user_identity, additional_claims={'admin': 1})


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


def extract_response_data(response):
    """
    Extract data from response handling both wrapped and direct formats.
    
    Some endpoints wrap responses in {"status": code, "data": {...}}
    Others return objects directly. This helper standardizes extraction.
    
    Args:
        response: Flask test client response
        
    Returns:
        dict or object: The actual data payload
    """
    try:
        data = response.get_json()
        if data is None:
            return {}
        # If response has 'data' key and it's the only data structure, extract it
        if isinstance(data, dict) and 'data' in data:
            return data.get('data', data)
        return data
    except Exception:
        return {}


def create_batch_in_context(app, batch_name, certificate_number, total_principal, **kwargs):
    """
    Create a batch safely within app context and return its ID + object.
    Ensures batch is properly flushed and accessible in tests.
    """
    with app.app_context():
        batch = Batch(
            batch_name=batch_name,
            certificate_number=certificate_number,
            total_principal=total_principal,
            **kwargs
        )
        db.session.add(batch)
        db.session.flush()  # Ensure batch gets an ID
        batch_id = batch.id
        db.session.commit()
    return batch_id


def create_investment_in_context(app, batch_id, investor_name, investor_email, internal_code, amount, **kwargs):
    """
    Create investment safely within app context and return its ID.
    Ensures batch_id is properly set.
    """
    with app.app_context():
        investment = Investment(
            batch_id=batch_id,
            investor_name=investor_name,
            investor_email=investor_email,
            internal_client_code=internal_code,
            amount_deposited=amount,
            date_deposited=datetime.now(timezone.utc),
            **kwargs
        )
        db.session.add(investment)
        db.session.flush()
        inv_id = investment.id
        db.session.commit()
    return inv_id



@pytest.fixture
def sample_batch(app):
    """
    Create a sample batch for testing.
    Returns batch object within app context.
    """
    with app.app_context():
        batch = Batch(
            batch_name='Test Batch 2026-Q1',
            certificate_number='CERT-2026-001',
            total_principal=Decimal('1000000.00'),
            duration_days=30,
            is_active=False,
            is_transferred=False,
            deployment_confirmed=False,
            stage=1,
        )
        db.session.add(batch)
        db.session.commit()
        batch_id = batch.id
        # Refresh to keep object in session
        db.session.refresh(batch)
    return batch


@pytest.fixture
def sample_batch_id(app):
    """
    Create a sample batch and return only its ID.
    Useful for tests that work with detached objects.
    """
    with app.app_context():
        batch = Batch(
            batch_name='Test Batch 2026-Q1',
            certificate_number='CERT-2026-001',
            total_principal=Decimal('1000000.00'),
            duration_days=30,
            is_active=False,
            is_transferred=False,
            deployment_confirmed=False,
            stage=1,
        )
        db.session.add(batch)
        db.session.commit()
        return batch.id


@pytest.fixture
def sample_investments(app, sample_batch):
    """
    Create sample investments for testing.
    Ensures batch_id is properly set.
    """
    with app.app_context():
        # Refresh batch to ensure it's in the current session
        batch = db.session.merge(sample_batch)
        
        investments = [
            Investment(
                investor_name='John Doe',
                investor_email='john@example.com',
                investor_phone='+1234567890',
                internal_client_code='INV-001',
                amount_deposited=Decimal('50000.00'),
                date_deposited=datetime.now(timezone.utc),
                batch_id=batch.id,  # Explicitly set
                wealth_manager='Jane Smith',
                IFA='Robert Johnson',
                contract_note='https://example.com/contract-001',
            ),
            Investment(
                investor_name='Alice Johnson',
                investor_email='alice@example.com',
                investor_phone='+9876543210',
                internal_client_code='INV-002',
                amount_deposited=Decimal('100000.00'),
                date_deposited=datetime.now(timezone.utc),
                batch_id=batch.id,  # Explicitly set
                wealth_manager='Jane Smith',
                IFA='Sarah Williams',
                contract_note='https://example.com/contract-002',
            ),
        ]
        db.session.add_all(investments)
        db.session.commit()
        # Refresh to keep in session
        for inv in investments:
            db.session.refresh(inv)
    return investments


@pytest.fixture
def sample_core_fund(app):
    """
    Create a sample fund for testing.
    """
    with app.app_context():
        fund = CoreFund(
            fund_name='OFDS-2026-Q1',
            fund_code='OFDS2601',
            asset_class='Private Equity',
            benchmark='MSCI World',
        )
        db.session.add(fund)
        db.session.commit()
        db.session.refresh(fund)
    return fund


@pytest.fixture
def sample_withdrawal(app, sample_investments, sample_core_fund):
    """
    Create a sample withdrawal for testing.
    """
    with app.app_context():
        # Merge objects to ensure they're in current session
        core_fund = db.session.merge(sample_core_fund)
        
        withdrawal = Withdrawal(
            internal_client_code='INV-001',
            fund_id=core_fund.id,
            fund_name=core_fund.fund_name,
            amount=Decimal('10000.00'),
            date_withdrawn=datetime.now(timezone.utc),
            status='Pending',
        )
        db.session.add(withdrawal)
        db.session.commit()
        db.session.refresh(withdrawal)
    return withdrawal


class MockEmailService:
    """Mock email service for testing without sending real emails"""
    
    sent_emails = []
    
    @classmethod
    def reset(cls):
        cls.sent_emails = []
    
    @classmethod
    def send_email(cls, to_email, subject, html_body):
        """Record email in sent_emails instead of sending"""
        cls.sent_emails.append({
            'to': to_email,
            'subject': subject,
            'body': html_body,
            'timestamp': datetime.now(timezone.utc),
        })
        return True
    
    @classmethod
    def get_sent_emails(cls, subject_filter=None):
        """Retrieve sent emails, optionally filtered by subject"""
        if subject_filter:
            return [e for e in cls.sent_emails if subject_filter in e['subject']]
        return cls.sent_emails


@pytest.fixture
def mock_email(monkeypatch):
    """
    Mock the email service to capture emails without sending.
    """
    MockEmailService.reset()
    
    # Patch the email sending function
    def mock_send(to_email, subject, html_body, **kwargs):
        MockEmailService.send_email(to_email, subject, html_body)
    
    # In your actual implementation, patch the email service directly
    # This depends on your email implementation
    return MockEmailService


# ==================== PYTEST COMMAND OPTIONS ====================
# Add to conftest.py for default pytest options

def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# ==================== HELPER FUNCTIONS ====================

def create_test_batch(name='Test Batch', stage=1, is_active=False, **kwargs):
    """Helper to create test batch with defaults"""
    defaults = {
        'batch_name': name,
        'certificate_number': f'CERT-{name.replace(" ", "-")}',
        'total_principal': Decimal('1000000.00'),
        'duration_days': 30,
        'stage': stage,
        'is_active': is_active,
        'is_transferred': False,
        'deployment_confirmed': False,
    }
    defaults.update(kwargs)
    batch = Batch(**defaults)
    db.session.add(batch)
    db.session.commit()
    return batch


def create_test_investment(batch_id, investor_name='Test Investor', **kwargs):
    """Helper to create test investment with defaults"""
    defaults = {
        'investor_name': investor_name,
        'investor_email': 'test@example.com',
        'investor_phone': '+1234567890',
        'internal_client_code': f'INV-{investor_name.replace(" ", "-")}',
        'amount_deposited': Decimal('50000.00'),
        'date_deposited': datetime.now(timezone.utc),
        'batch_id': batch_id,
        'wealth_manager': 'Test Manager',
        'IFA': 'Test IFA',
    }
    defaults.update(kwargs)
    investment = Investment(**defaults)
    db.session.add(investment)
    db.session.commit()
    return investment
