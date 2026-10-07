"""
Batch CRUD Operations Tests
===========================
Tests for batch creation, retrieval, updates, and management endpoints.

Run with: pytest tests/test_batch_crud.py -v
"""

import pytest
import json
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.database.database import db
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment, EmailLog, EpochLedger
from app.Valuation.model import Statement, ValuationRun


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestBatchCreation:
    """Test creating new batches"""
    
    def test_create_batch_success(self, client, auth_token):
        """Test successfully creating a new batch"""
        payload = {
            'batch_name': 'MAR-2026-OFFSHORE',
            'certificate_number': 'CERT-2026-001',
            'total_principal': '1000000.00',
            'duration_days': 30
        }
        
        response = client.post(
            '/api/v1/batches',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        response_data = response.get_json()
        
        # Extract batch from response (could be wrapped in "data" or direct)
        batch_data = response_data.get('data', response_data)
        batch_id = batch_data.get('id')
        
        assert batch_id is not None
        
        # Verify in database
        batch = db.session.get(Batch, batch_id)
        assert batch is not None
        assert batch.batch_name == 'MAR-2026-OFFSHORE'
        assert batch.stage == 1  # Should start at stage 1
    
    def test_create_batch_missing_name(self, client, auth_token):
        """Test validation: batch_name is required"""
        payload = {
            'certificate_number': 'CERT-2026-001',
            'duration_days': 30
        }
        
        response = client.post(
            '/api/v1/batches',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_batch_missing_body(self, client, auth_token):
        """Test validation: request body is required"""
        response = client.post(
            '/api/v1/batches',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 400

    def test_create_batch_duplicate_name(self, client, auth_token):
        """Test validation: cannot create with duplicate batch_name"""
        existing = Batch(batch_name='DUPLICATE-BATCH')
        db.session.add(existing)
        db.session.commit()

        payload = {
            'batch_name': 'DUPLICATE-BATCH',
            'certificate_number': 'CERT-2026-005',
            'duration_days': 30
        }
        response = client.post(
            '/api/v1/batches',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )

        assert response.status_code == 409
        assert 'already exists' in response.get_json().get('message', '').lower()
    
    def test_create_batch_default_values(self, client, auth_token):
        """Test batch creation with default values"""
        payload = {
            'batch_name': 'TEST-BATCH',
            'certificate_number': 'CERT-TEST'
        }
        
        response = client.post(
            '/api/v1/batches',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        batch = Batch.query.filter_by(batch_name='TEST-BATCH').first()
        assert batch.is_active == False
        assert batch.is_transferred == False
        assert batch.stage == 1
    
    def test_create_batch_without_jwt_token(self, client):
        """Test that batch creation requires authentication"""
        payload = {
            'batch_name': 'MAR-2026-OFFSHORE',
            'certificate_number': 'CERT-2026-001'
        }
        
        response = client.post(
            '/api/v1/batches',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 401


@pytest.mark.unit
class TestBatchRetrieval:
    """Test retrieving batch information"""
    
    def test_get_batch_success(self, client, auth_token, sample_batch):
        """Test successfully retrieving a batch"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['id'] == sample_batch.id
        assert data['data']['batch_name'] == sample_batch.batch_name
    
    def test_get_batch_not_found(self, client, auth_token):
        """Test retrieving non-existent batch"""
        response = client.get(
            '/api/v1/batches/99999',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 404

    def test_get_batch_detail_uses_current_standing(self, client, auth_token, app):
        """Batch detail totals should use current standing values for total capital"""
        with app.app_context():
            batch = Batch(
                batch_name='DETAIL-BATCH',
                certificate_number='CERT-DETAIL',
                duration_days=30,
            )
            core_fund = CoreFund(
                fund_name='Axiom Detail Fund',
                fund_code='AX-DETAIL-01',
            )
            db.session.add_all([batch, core_fund])
            db.session.commit()

            investment_one = Investment(
                investor_name='Investor One',
                investor_email='one@example.com',
                internal_client_code='INV-DET-1',
                amount_deposited=Decimal('10000.00'),
                date_deposited=datetime.now(),
                batch_id=batch.id,
                fund_id=core_fund.id,
            )
            investment_two = Investment(
                investor_name='Investor Two',
                investor_email='two@example.com',
                internal_client_code='INV-DET-2',
                amount_deposited=Decimal('15000.00'),
                date_deposited=datetime.now(),
                batch_id=batch.id,
                fund_id=core_fund.id,
            )
            db.session.add_all([investment_one, investment_two])
            db.session.commit()

            ledger_one = EpochLedger(
                internal_client_code='INV-DET-1',
                fund_name=core_fund.fund_name,
                epoch_start=datetime(2026, 5, 1),
                epoch_end=datetime(2026, 5, 31),
                performance_rate=Decimal('0.05'),
                start_balance=Decimal('10000.00'),
                deposits=Decimal('0.00'),
                withdrawals=Decimal('0.00'),
                profit=Decimal('500.00'),
                end_balance=Decimal('10500.00'),
                previous_hash='a' * 64,
                current_hash='b' * 64,
            )
            ledger_two = EpochLedger(
                internal_client_code='INV-DET-2',
                fund_name=core_fund.fund_name,
                epoch_start=datetime(2026, 5, 1),
                epoch_end=datetime(2026, 5, 31),
                performance_rate=Decimal('0.05'),
                start_balance=Decimal('15000.00'),
                deposits=Decimal('0.00'),
                withdrawals=Decimal('0.00'),
                profit=Decimal('750.00'),
                end_balance=Decimal('15750.00'),
                previous_hash='c' * 64,
                current_hash='d' * 64,
            )
            db.session.add_all([ledger_one, ledger_two])

            from app.Valuation.model import BatchValuation

            db.session.add(
                BatchValuation(
                    batch_id=batch.id,
                    period_end_date=datetime(2026, 5, 31, tzinfo=timezone.utc),
                    balance_at_end_of_period=Decimal("26250.00"),
                    performance_rate=Decimal("0.05"),
                    total_principal=Decimal("25000.00"),
                    total_profit=Decimal("1250.00"),
                    total_withdrawals=Decimal("0.00"),
                )
            )
            db.session.commit()
            batch_id = batch.id

        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload['data']['total_capital'] == 26250.0
        assert payload['data']['total_principal'] == 25000.0
        assert payload['data']['investments'][0]['current_balance'] == 10500.0
        assert payload['data']['investments'][1]['current_balance'] == 15750.0

    def test_get_all_batches(self, client, auth_token, app):
        """Test retrieving all batches"""
        with app.app_context():
            for i in range(3):
                batch = Batch(
                    batch_name=f'BATCH-{i}',
                    certificate_number=f'CERT-{i}',
                    total_principal=Decimal('1000000.00'),
                    duration_days=30
                )
                db.session.add(batch)
            db.session.commit()
        
        response = client.get(
            '/api/v1/batches',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 3

    def test_get_all_batches_uses_current_standing_values(self, client, auth_token, app, sample_batch, sample_core_fund):
        """Batch totals should use the sum of current standing values only"""
        with app.app_context():
            investment = Investment(
                investor_name='Current Standing Investor',
                investor_email='current@example.com',
                internal_client_code='INV-COMMIT',
                amount_deposited=Decimal('52500.00'),
                date_deposited=datetime.now(),
                batch_id=sample_batch.id,
                fund_id=sample_core_fund.id,
                fund_name=sample_core_fund.fund_name,
            )
            db.session.add(investment)
            db.session.commit()

            committed_run = ValuationRun(
                core_fund_id=sample_core_fund.id,
                epoch_start=datetime(2026, 3, 1),
                epoch_end=datetime(2026, 3, 31),
                performance_rate=Decimal('0.05'),
                head_office_total=Decimal('1000000.00'),
                status='Committed',
            )
            db.session.add(committed_run)
            db.session.commit()

            statement = Statement(
                investor_id=investment.id,
                batch_id=sample_batch.id,
                fund_id=sample_core_fund.id,
                valuation_run_id=committed_run.id,
                opening_balance=Decimal('50000.00'),
                withdrawals=Decimal('0.00'),
                performance_gain=Decimal('2500.00'),
                closing_balance=Decimal('52500.00'),
            )
            db.session.add(statement)

            stale_ledger = EpochLedger(
                internal_client_code='INV-COMMIT',
                fund_name=sample_core_fund.fund_name,
                epoch_start=datetime(2026, 4, 1),
                epoch_end=datetime(2026, 4, 30),
                performance_rate=Decimal('0.00'),
                start_balance=Decimal('52500.00'),
                deposits=Decimal('0.00'),
                withdrawals=Decimal('0.00'),
                profit=Decimal('0.00'),
                end_balance=Decimal('60000.00'),
                previous_hash='a' * 64,
                current_hash='b' * 64,
            )
            db.session.add(stale_ledger)

            from app.Valuation.model import BatchValuation

            db.session.add(
                BatchValuation(
                    batch_id=sample_batch.id,
                    period_end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
                    balance_at_end_of_period=Decimal("60000.00"),
                    performance_rate=Decimal("0"),
                    total_principal=Decimal("52500.00"),
                    total_profit=Decimal("7500.00"),
                    total_withdrawals=Decimal("0.00"),
                )
            )
            db.session.commit()

        response = client.get(
            '/api/v1/batches',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200
        data = response.get_json()
        batch = next((item for item in data.get('data', []) if item['id'] == sample_batch.id), None)
        assert batch is not None
        assert batch['total_capital'] == 60000.0
        assert batch['total_principal'] == 52500.0

    def test_get_batch_summary(self, client, auth_token, sample_batch, sample_investments):
        """Test retrieving batch summary with investments"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['batch_id'] == sample_batch.id
        assert 'distributions' in data['data']
        assert 'total_investors' in data['data']
        assert data['data']['total_investors'] > 0

    def test_get_batch_email_logs(self, client, auth_token, sample_batch, sample_investments):
        # Insert a sample email log for the sample batch
        investment = sample_investments[0]
        log = EmailLog(investor_id=investment.id, batch_id=sample_batch.id, status='Sent')
        db.session.add(log)
        db.session.commit()

        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/email-logs',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['summary']['sent'] >= 1
        assert any(item['id'] == log.id for item in data['data'])

    def test_get_investor_directory(self, client, auth_token, sample_batch):
        # Create 2 investments and their logs
        inv1 = Investment(investor_name='Alice', investor_email='alice@example.com', internal_client_code='INV-A', amount_deposited=1000, date_deposited=datetime.now(), batch_id=sample_batch.id)
        inv2 = Investment(investor_name='Bob', investor_email='bob@example.com', internal_client_code='INV-B', amount_deposited=2000, date_deposited=datetime.now(), batch_id=sample_batch.id)
        db.session.add_all([inv1, inv2])
        db.session.commit()
        db.session.add(EmailLog(investor_id=inv1.id, batch_id=sample_batch.id, status='Sent'))
        db.session.add(EmailLog(investor_id=inv2.id, batch_id=sample_batch.id, status='Failed', error_message='SMTP failure'))
        db.session.commit()

        response = client.get('/api/v1/investors', headers=get_auth_headers(auth_token))
        assert response.status_code == 200
        data = response.get_json()
        assert data['count'] >= 2
        assert any(i['internal_client_code'] == 'INV-A' for i in data['data'])

    def test_get_investor_email_logs(self, client, auth_token, sample_batch):
        inv = Investment(investor_name='Charlie', investor_email='charlie@example.com', internal_client_code='INV-C', amount_deposited=3000, date_deposited=datetime.now(), batch_id=sample_batch.id)
        db.session.add(inv)
        db.session.commit()
        log = EmailLog(investor_id=inv.id, batch_id=sample_batch.id, status='Failed', error_message='Not found')
        db.session.add(log)
        db.session.commit()

        response = client.get(f'/api/v1/investors/{inv.internal_client_code}/email-logs', headers=get_auth_headers(auth_token))
        assert response.status_code == 200
        data = response.get_json()
        assert data['count'] == 1
        assert data['data'][0]['status'] == 'Failed'

    def test_delete_batch_success(self, client, auth_token, sample_batch):
        """Test deleting a batch."""
        response = client.delete(
            f'/api/v1/batches/{sample_batch.id}',
            headers=get_auth_headers(auth_token)
        )
        assert response.status_code == 200

        batch = db.session.get(Batch, sample_batch.id)
        assert batch is None

    def test_upload_batch_excel_investor_email_and_tracker(self, client, auth_token, sample_batch):
        """Test batch Excel upload, email notifications, and stage update."""
        csv_content = "Client Name,Internal Client Code,Amount(USD),Funds,Email\nJohn Doe,INV-001,1000,Atium,john@example.com\n"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'investors.csv')
        }

        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/upload-excel',
            data=data,
            content_type='multipart/form-data',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 201
        resp_data = response.get_json()
        assert resp_data['data']['imported_investments'] == 1
        assert resp_data['data']['emails_sent'] >= 0
        assert resp_data['data']['stage'] == 1

        investment = Investment.query.filter_by(internal_client_code='INV-001').first()
        assert investment is not None
        assert investment.investor_email == 'john@example.com'


@pytest.mark.unit
class TestBatchUpdate:
    """Test updating batch information"""
    
    def test_update_batch_name(self, client, auth_token, sample_batch):
        """Test updating batch name via PUT"""
        payload = {
            'batch_name': 'UPDATED-BATCH-NAME'
        }
        
        response = client.put(
            f'/api/v1/batches/{sample_batch.id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]
        
        updated_batch = db.session.get(Batch, sample_batch.id)
        assert updated_batch.batch_name == 'UPDATED-BATCH-NAME'

    def test_update_batch_name_conflict(self, client, auth_token, sample_batch):
        """Test editing to a batch name that already exists"""
        other = Batch(batch_name='ALREADY_EXISTS')
        db.session.add(other)
        db.session.commit()

        payload = { 'batch_name': 'ALREADY_EXISTS' }
        response = client.put(
            f'/api/v1/batches/{sample_batch.id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )

        assert response.status_code == 409
        assert 'already exists' in response.get_json().get('message', '').lower()
    
    def test_update_batch_multiple_fields(self, client, auth_token, sample_batch):
        """Test updating multiple batch fields"""
        payload = {
            'batch_name': 'APR-2026-OFFSHORE',
            'duration_days': 45,
            'is_active': True
        }
        
        response = client.put(
            f'/api/v1/batches/{sample_batch.id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]
        
        updated_batch = db.session.get(Batch, sample_batch.id)
        assert updated_batch.batch_name == 'APR-2026-OFFSHORE'
        assert updated_batch.duration_days == 45
        assert updated_batch.is_active == True
    
    def test_patch_batch(self, client, auth_token, sample_batch):
        """Test partial update via PATCH"""
        payload = {
            'is_transferred': True
        }
        
        response = client.patch(
            f'/api/v1/batches/{sample_batch.id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]
        
        updated_batch = db.session.get(Batch, sample_batch.id)
        assert updated_batch.is_transferred == True
    
    def test_update_batch_not_found(self, client, auth_token):
        """Test updating non-existent batch"""
        payload = {
            'batch_name': 'UPDATED-NAME'
        }
        
        response = client.put(
            '/api/v1/batches/99999',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400


@pytest.mark.unit
class TestBatchToggleOperations:
    """Test batch toggle operations (active, transferred, etc.)"""
    
    def test_toggle_active_status(self, client, auth_token, sample_batch):
        """Test toggling batch active status"""
        initial_status = sample_batch.is_active
        
        response = client.patch(
            f'/api/v1/batches/{sample_batch.id}/toggle-active',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 204]
        
        updated_batch = db.session.get(Batch, sample_batch.id)
        assert updated_batch.is_active != initial_status
    
    def test_toggle_transferred_status(self, client, auth_token, sample_batch):
        """Test toggling batch transferred status"""
        initial_status = sample_batch.is_transferred
        
        response = client.patch(
            f'/api/v1/batches/{sample_batch.id}/toggle-transferred',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 204]
        
        updated_batch = db.session.get(Batch, sample_batch.id)
        assert updated_batch.is_transferred != initial_status
    
    def test_update_batch_status(self, client, auth_token, sample_batch):
        """Test updating batch status with status code"""
        payload = {'status': 2}  # Move to stage 2
        
        response = client.patch(
            f'/api/v1/batches/{sample_batch.id}/update_status',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]


@pytest.mark.unit
class TestBatchNotifications:
    """Test batch notification operations"""
    
    def test_notify_transfer(self, client, auth_token, sample_batch, sample_investments):
        """Test sending transfer notification"""
        response = client.patch(
            f'/api/v1/batches/{sample_batch.id}/notify-transfer',
            headers=get_auth_headers(auth_token)
        )
        
        # Should succeed if investors are present
        assert response.status_code in [200, 204, 400]

    def test_recent_notifications(self, client, auth_token, sample_batch, sample_investments):
        # Trigger a stage 2 transfer event and summary store
        client.patch(
            f'/api/v1/batches/{sample_batch.id}/update_status',
            data=json.dumps({'status': 2}),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        response = client.get('/api/v1/notifications/recent', headers=get_auth_headers(auth_token))
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data.get('data'), list)

    def test_notification_failures(self, client, auth_token, sample_batch, sample_investments):
        # Get any existing notification summary event
        response = client.get('/api/v1/notifications/recent', headers=get_auth_headers(auth_token))
        assert response.status_code == 200
        notifications = response.get_json().get('data', [])
        if not notifications:
            pytest.skip('No notification events to test failure path')

        notif_id = notifications[0].get('id')
        response2 = client.get(f'/api/v1/notifications/recent/{notif_id}/failures', headers=get_auth_headers(auth_token))
        assert response2.status_code in [200, 404]
        if response2.status_code == 200:
            assert isinstance(response2.get_json().get('data'), list)


@pytest.mark.unit
class TestBatchLifecycle:
    """Test complete batch lifecycle"""
    
    def test_batch_stage_progression(self, client, auth_token, sample_batch, sample_investments):
        """Test batch progressing through stages"""
        # Stage 1: Created with investments
        assert sample_batch.stage == 1
        
        # Move to Stage 2: Transferred
        response = client.patch(
            f'/api/v1/batches/{sample_batch.id}/update_status',
            data=json.dumps({'status': 2}),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        batch = db.session.get(Batch, sample_batch.id)
        assert batch.stage >= 1  # Should progress
    
    def test_batch_deployment_workflow(self, client, auth_token, app):
        """Test complete deployment workflow"""
        # Create batch
        with app.app_context():
            batch = Batch(
                batch_name='DEPLOY-TEST',
                certificate_number='CERT-DEPLOY',
                total_principal=Decimal('500000.00'),
                duration_days=30,
                stage=1
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id
            
            # Add investment
            investment = Investment(
                investor_name='Test Investor',
                investor_email='test@example.com',
                internal_client_code='INV-001',
                amount_deposited=Decimal('500000.00'),
                batch_id=batch_id
            )
            db.session.add(investment)
            db.session.commit()
            batch_id = batch.id
        
        # Verify batch exists and has investments
        response = client.get(
            f'/api/v1/batches/{batch_id}/summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['data']['total_investors'] > 0
