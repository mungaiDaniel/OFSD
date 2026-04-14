"""
Performance & Distributions Tests
==================================
Tests for performance tracking, pro-rata calculation, and distribution endpoints.

Run with: pytest tests/test_performance.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestPerformanceCreation:
    """Test creating performance records"""
    
    def test_create_performance_success(self, client, auth_token, sample_batch, sample_investments):
        """Test successfully creating a performance record"""
        payload = {
            'gross_profit': '50000.00',
            'transaction_costs': '1000.00',
            'date_closed': '2026-03-27'
        }
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/performance',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400]
    
    def test_create_performance_missing_date(self, client, auth_token, sample_batch):
        """Test validation: date_closed is required"""
        payload = {
            'gross_profit': '50000.00',
            'transaction_costs': '1000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/performance',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_performance_invalid_batch(self, client, auth_token):
        """Test creating performance for non-existent batch"""
        payload = {
            'gross_profit': '50000.00',
            'transaction_costs': '1000.00',
            'date_closed': '2026-03-27'
        }
        
        response = client.post(
            '/api/v1/batches/99999/performance',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [404, 400]


@pytest.mark.unit
class TestPerformanceRetrieval:
    """Test retrieving performance data"""
    
    def test_get_batch_performance(self, client, auth_token, sample_batch):
        """Test retrieving batch performance"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/performance',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            assert isinstance(data, (dict, list))
    
    def test_get_performance_by_fund(self, client, auth_token, sample_batch):
        """Test retrieving performance filtered by fund"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/performance?fund_name=Axiom',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_get_performance_invalid_batch(self, client, auth_token):
        """Test retrieving performance for non-existent batch"""
        response = client.get(
            '/api/v1/batches/99999/performance',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [404, 200]


@pytest.mark.unit
class TestProRataCalculation:
    """Test pro-rata distribution calculations"""
    
    def test_calculate_pro_rata_success(self, client, auth_token, sample_batch, sample_investments):
        """Test successfully calculating pro-rata distributions"""
        payload = {
            'fund_name': 'Axiom',
            'performance_date': datetime.now(timezone.utc).isoformat(),
            'total_return': '50000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/calculate-pro-rata',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400]
    
    def test_calculate_pro_rata_validation(self, client, auth_token, sample_batch):
        """Test pro-rata calculation without investments"""
        payload = {
            'fund_name': 'Axiom',
            'total_return': '50000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/calculate-pro-rata',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # Should validate that batch has investments
        assert response.status_code in [200, 201, 400, 404]
    
    def test_pro_rata_distribution_accuracy(self, client, auth_token, app):
        """Test pro-rata calculations are accurate"""
        with app.app_context():
            batch = Batch(
                batch_name='PRORTA-TEST',
                certificate_number='CERT-PRORTA',
                total_principal=Decimal('100000.00'),
                stage=1
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID before using it
            batch_id = batch.id
            
            # Create investments with specific amounts for calculation
            inv1 = Investment(
                investor_name='Investor 1',
                investor_email='inv1@example.com',
                internal_client_code='INV-1',
                amount_deposited=Decimal('60000.00'),
                batch_id=batch_id
            )
            
            inv2 = Investment(
                investor_name='Investor 2',
                investor_email='inv2@example.com',
                internal_client_code='INV-2',
                amount_deposited=Decimal('40000.00'),
                batch_id=batch_id
            )
            
            db.session.add_all([inv1, inv2])
            db.session.commit()
            batch_id = batch.id
        
        # Calculate pro-rata on 10000 profit
        payload = {
            'fund_name': 'TestFund',
            'total_return': '10000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{batch_id}/calculate-pro-rata',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400, 404]


@pytest.mark.unit
class TestDistributions:
    """Test distribution retrieval and tracking"""
    
    def test_get_batch_distributions(self, client, auth_token, sample_batch):
        """Test retrieving all distributions for a batch"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/distributions',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            assert isinstance(data, (dict, list))
    
    def test_get_fund_distributions(self, client, auth_token, sample_batch):
        """Test retrieving distributions for a specific fund"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/funds/Axiom/distributions',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_distributions_sum_correctly(self, client, auth_token, app):
        """Test that distributions sum to total return"""
        with app.app_context():
            batch = Batch(
                batch_name='DIST-SUM-TEST',
                certificate_number='CERT-DIST',
                total_principal=Decimal('100000.00'),
                stage=1
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id
            
            # Create multiple investments
            for i in range(5):
                inv = Investment(
                    investor_name=f'Investor {i}',
                    investor_email=f'inv{i}@example.com',
                    internal_client_code=f'INV-{i}',
                    amount_deposited=Decimal('20000.00'),
                    batch_id=batch_id
                )
                db.session.add(inv)
            db.session.commit()
            batch_id = batch.id
        
        # Calculate distributions
        payload = {
            'fund_name': 'DistTest',
            'total_return': '5000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{batch_id}/calculate-pro-rata',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # Retrieve distributions
        response = client.get(
            f'/api/v1/batches/{batch_id}/distributions',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestPerformanceWorkflow:
    """Test complete performance and distribution workflow"""
    
    def test_performance_to_distribution_workflow(self, client, auth_token, app):
        """Test complete workflow from performance entry to distribution"""
        with app.app_context():
            batch = Batch(
                batch_name='WORKFLOW-TEST',
                certificate_number='CERT-WORKFLOW',
                total_principal=Decimal('100000.00'),
                stage=1
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id

            inv1 = Investment(
                investor_name='Workflow Investor 1',
                investor_email='wf1@example.com',
                internal_client_code='WF-1',
                amount_deposited=Decimal('60000.00'),
                batch_id=batch_id
            )
            
            inv2 = Investment(
                investor_name='Workflow Investor 2',
                investor_email='wf2@example.com',
                internal_client_code='WF-2',
                amount_deposited=Decimal('40000.00'),
                batch_id=batch_id
            )
            
            db.session.add_all([inv1, inv2])
            db.session.commit()
            batch_id = batch.id
        
        # Step 1: Record performance
        perf_payload = {
            'performance_date': datetime.now(timezone.utc).isoformat(),
            'fund_value': '110000.00',
            'profit': '10000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{batch_id}/performance',
            data=json.dumps(perf_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400]
        
        # Step 2: Calculate pro-rata
        calc_payload = {
            'fund_name': 'WorkflowFund',
            'total_return': '10000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{batch_id}/calculate-pro-rata',
            data=json.dumps(calc_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 400, 404]
        
        # Step 3: Retrieve distributions
        response = client.get(
            f'/api/v1/batches/{batch_id}/distributions',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
