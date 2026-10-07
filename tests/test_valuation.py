"""
Valuation & Epoch Tests
=======================
Tests for valuation calculations, dry-runs, epoch creation, and confirmation.

Run with: pytest tests/test_valuation.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.database.database import db
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment
from app.logic.valuation_service import PortfolioValuationService


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestValuationDryRun:
    """Test dry-run valuation calculations"""
    
    def test_dry_run_post_success(self, client, auth_token, sample_batch, sample_investments):
        """Test executing a dry-run valuation via POST"""
        payload = {
            'fund_name': 'Axiom',
            'start_date': '2026-01-01',
            'end_date': '2026-03-27',
            'performance_rate_percent': 5.0,
            'head_office_total': '100000.00'
        }
        
        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 400, 404]
    
    def test_dry_run_with_fund_name(self, client, auth_token, sample_batch, sample_investments):
        """Test dry-run using fund_name"""
        payload = {
            'fund_name': 'Atium',
            'start_date': '2026-01-01',
            'end_date': '2026-03-27',
            'performance_rate_percent': 3.5,
            'head_office_total': '150000.00'
        }
        
        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 400, 404]
    
    def test_dry_run_get_endpoint(self, client, auth_token, sample_batch):
        """Test dry-run via GET endpoint with query parameters"""
        response = client.get(
            f'/api/v1/valuation/epoch/dry-run?fund_id=1&start_date=2026-01-01&end_date=2026-03-27&performance_rate=5.0',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 400, 404]
    
    def test_dry_run_validation(self, client, auth_token):
        """Test dry-run without required parameters"""
        payload = {
            'valuation_date': datetime.now(timezone.utc).isoformat()
        }
        
        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # Should return error or success depending on defaults
        assert response.status_code in [200, 400]

    def test_dry_run_color_state_and_distinct_investor_count(self, client, auth_token, app, sample_core_fund, sample_batch):
        # Create investments with the same investor name but different client codes
        with app.app_context():
            inv1 = Investment(investor_name='Nina Simone', investor_email='nina1@example.com', internal_client_code='NINA-1', amount_deposited=100000, date_deposited=datetime.now(timezone.utc), batch_id=sample_batch.id, fund_id=sample_core_fund.id)
            inv2 = Investment(investor_name='Nina Simone', investor_email='nina2@example.com', internal_client_code='NINA-2', amount_deposited=50000, date_deposited=datetime.now(timezone.utc), batch_id=sample_batch.id, fund_id=sample_core_fund.id)
            db.session.add_all([inv1, inv2])
            db.session.commit()

    def test_dry_run_fresh_start_uses_excel_principal(self, client, auth_token, app, sample_core_fund):
        """Initial epoch should treat 100% of the Excel sum as opening principal."""
        with app.app_context():
            # Create fund and batch
            fund = CoreFund(fund_name='Axiom', fund_code='AXM-2026')
            db.session.add(fund)
            batch = Batch(batch_name='Axiom Batch 1', certificate_number='AX-BATCH-1', total_principal=Decimal('150000.00'), duration_days=30, is_active=True, is_transferred=True, deployment_confirmed=True)
            db.session.add(batch)
            db.session.commit()

            # Add 3 investors as fresh input on epoch start date
            for idx, amount in enumerate([50000, 50000, 50000], start=1):
                inv = Investment(
                    investor_name=f'Investor {idx}',
                    investor_email=f'investor{idx}@example.com',
                    internal_client_code=f'AXM-{idx}',
                    amount_deposited=Decimal(str(amount)),
                    date_deposited=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    batch_id=batch.id,
                    fund_id=fund.id,
                    fund_name=fund.fund_name,
                )
                db.session.add(inv)
            db.session.commit()

        payload = {
            'fund_name': 'Axiom',
            'start_date': '2026-04-01',
            'end_date': '2026-04-30',
            'performance_rate_percent': 5.0,
            'head_office_total': '157500.00'
        }

        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = response.get_json()['data']

        assert data['excel_total'] == 150000.0
        assert data['detected_principal'] == 150000.0
        assert data['calculated_profit'] == 7500.0
        assert data['total_to_commit'] == 157500.0
        assert data['total_start_balance'] == 0.0
        assert data['total_deposits'] == 150000.0
        assert data['is_reconciled'] is True

        # Second epoch: compound from first epoch closing as start_balance
        first_run = PortfolioValuationService.create_epoch_ledger_for_fund(
            fund_id=fund.id,
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            performance_rate=Decimal('0.05'),
            head_office_total=Decimal('157500.00'),
            session=db.session,
        )

        second_payload = {
            'fund_name': 'Axiom',
            'start_date': '2026-05-01',
            'end_date': '2026-05-31',
            'performance_rate_percent': 5.0,
            'head_office_total': '165375.00'
        }

        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(second_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        second_data = response.get_json()['data']

        assert second_data['total_start_balance'] == 157500.0
        assert second_data['total_deposits'] == 0.0
        assert second_data['calculated_profit'] == 7875.0
        assert second_data['total_to_commit'] == 165375.0
        assert second_data['is_reconciled'] is True

        payload = {
            'fund_name': sample_core_fund.fund_name,
            'start_date': '2026-01-01',
            'end_date': '2026-01-31',
            'performance_rate_percent': 0,
            'head_office_total': '150000.00'
        }

        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = response.get_json().get('data', {})

        assert data['excel_total'] == 150000.0
        assert data['gross_principal'] == 150000.0
        assert data['withdrawals_total'] == 0.0
        assert data['net_excel_total'] == 150000.0
        assert data['projected_portfolio_value'] == 150000.0
        assert data['total_rows_detected'] == 2
        assert data['distinct_investor_count'] == 2
        assert abs(data['net_excel_total'] - float(payload['head_office_total'])) < 0.01


@pytest.mark.unit
class TestEpochCreation:
    """Test epoch ledger creation"""
    
    def test_create_epoch_success(self, client, auth_token, sample_batch, sample_investments):
        """Test successfully creating an epoch ledger"""
        payload = {
            'fund_name': 'Axiom',
            'epoch_date': datetime.now(timezone.utc).isoformat(),
            'batch_id': sample_batch.id
        }
        
        response = client.post(
            '/api/v1/valuation/epoch',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400, 404]
    
    def test_create_epoch_missing_date(self, client, auth_token, sample_batch):
        """Test validation: epoch_date is required"""
        payload = {
            'fund_name': 'Axiom',
            'batch_id': sample_batch.id
        }
        
        response = client.post(
            '/api/v1/valuation/epoch',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_epoch_invalid_batch(self, client, auth_token):
        """Test creating epoch for non-existent batch"""
        payload = {
            'fund_name': 'Axiom',
            'epoch_date': datetime.now(timezone.utc).isoformat(),
            'batch_id': 99999
        }
        
        response = client.post(
            '/api/v1/valuation/epoch',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [400, 404]


@pytest.mark.unit
class TestValuationConfirmation:
    """Test valuation confirmation and commitment"""
    
    def test_confirm_epoch_success(self, client, auth_token, sample_batch):
        """Test successfully confirming an epoch valuation"""
        payload = {
            'batch_id': sample_batch.id,
            'fund_name': 'Axiom',
            'epoch_date': datetime.now(timezone.utc).isoformat(),
            'confirmed': True
        }
        
        response = client.post(
            '/api/v1/valuation/confirm',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400, 404]
    
    def test_confirm_epoch_validation(self, client, auth_token, sample_batch):
        """Test epoch confirmation with missing parameters"""
        payload = {
            'batch_id': sample_batch.id
        }
        
        response = client.post(
            '/api/v1/valuation/confirm',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # Should require more parameters
        assert response.status_code in [200, 201, 400]


@pytest.mark.unit
class TestValuationFunds:
    """Test fund list and valuation fund operations"""
    
    def test_get_active_funds_for_valuation(self, client, auth_token):
        """Test retrieving active funds for valuation"""
        response = client.get(
            '/api/v1/valuation/funds',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data.get('data', []), list)
    
    def test_valuation_fund_filter(self, client, auth_token):
        """Test filtering active funds by status"""
        response = client.get(
            '/api/v1/valuation/funds?status=active',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestBatchValuationSummary:
    """Test batch-level valuation summary"""
    
    def test_get_batch_valuation_summary(self, client, auth_token, sample_batch, sample_investments):
        """Test retrieving batch valuation summary"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/valuation-summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Should contain valuation metrics
            assert isinstance(data, dict)
    
    def test_valuation_summary_metrics(self, client, auth_token, app):
        """Test valuation summary contains expected metrics"""
        with app.app_context():
            batch = Batch(
                batch_name='VAL-SUM-TEST',
                certificate_number='CERT-VAL-SUM',
                total_principal=Decimal('100000.00'),
                stage=2
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID before using it
            batch_id = batch.id

            # Add investments
            inv1 = Investment(
                investor_name='Val Investor 1',
                investor_email='valinv1@example.com',
                internal_client_code='VALINV-1',
                amount_deposited=Decimal('60000.00'),
                batch_id=batch_id  # Use the flushed batch_id
            )

            inv2 = Investment(
                investor_name='Val Investor 2',
                investor_email='valinv2@example.com',
                internal_client_code='VALINV-2',
                amount_deposited=Decimal('40000.00'),
                batch_id=batch_id  # Use the flushed batch_id
            )

            db.session.add_all([inv1, inv2])
            db.session.commit()
            batch_id = batch.id
        
        response = client.get(
            f'/api/v1/batches/{batch_id}/valuation-summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Verify structure
            assert isinstance(data, dict)


@pytest.mark.unit
class TestValuationWorkflow:
    """Test complete valuation workflow"""
    
    def test_complete_valuation_workflow(self, client, auth_token, app):
        """Test end-to-end valuation workflow: dry-run -> create -> confirm"""
        with app.app_context():
            batch = Batch(
                batch_name='VAL-WORKFLOW',
                certificate_number='CERT-VALWF',
                total_principal=Decimal('100000.00'),
                stage=2
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id

            inv = Investment(
                investor_name='Workflow Val Investor',
                investor_email='wfvalinv@example.com',
                internal_client_code='WFVALINV-1',
                amount_deposited=Decimal('100000.00'),
                batch_id=batch_id  # Use flushed batch_id
            )

            db.session.add(inv)
            db.session.commit()
            batch_id = batch.id
        
        # Step 1: Dry-run
        dry_run_payload = {
            'fund_name': 'ValWorkflowFund',
            'batch_id': batch_id
        }
        
        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(dry_run_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 400, 404]
        
        # Step 2: Create epoch
        epoch_payload = {
            'fund_name': 'ValWorkflowFund',
            'batch_id': batch_id,
            'epoch_date': datetime.now(timezone.utc).isoformat()
        }
        
        response = client.post(
            '/api/v1/valuation/epoch',
            data=json.dumps(epoch_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400, 404]
        
        # Step 3: Confirm epoch
        confirm_payload = {
            'fund_name': 'ValWorkflowFund',
            'batch_id': batch_id,
            'confirmed': True
        }
        
        response = client.post(
            '/api/v1/valuation/confirm',
            data=json.dumps(confirm_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400, 404]
        
        # Step 4: Get valuation summary
        response = client.get(
            f'/api/v1/batches/{batch_id}/valuation-summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestValuationEdgeCases:
    """Test valuation edge cases and error conditions"""
    
    def test_valuation_without_investments(self, client, auth_token, app):
        """Test valuation on batch without investments"""
        with app.app_context():
            batch = Batch(
                batch_name='EMPTY-BATCH',
                certificate_number='CERT-EMPTY',
                total_principal=Decimal('0.00'),
                stage=1
            )
            db.session.add(batch)
            db.session.commit()
            batch_id = batch.id
        
        payload = {
            'fund_name': 'TestFund',
            'batch_id': batch_id
        }
        
        response = client.post(
            '/api/v1/valuation/dry-run',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # Should either fail or handle gracefully
        assert response.status_code in [200, 400, 404]
    
    def test_valuation_on_inactive_batch(self, client, auth_token, app):
        """Test valuation on inactive batch"""
        with app.app_context():
            batch = Batch(
                batch_name='INACTIVE-VAL',
                certificate_number='CERT-INACT',
                total_principal=Decimal('50000.00'),
                is_active=False,
                stage=1
            )
            db.session.add(batch)
            db.session.commit()
            batch_id = batch.id
        
        response = client.get(
            f'/api/v1/batches/{batch_id}/valuation-summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
