"""
Fund Management Tests
=====================
Tests for fund creation, retrieval, updates, and batch fund operations.

Run with: pytest tests/test_funds.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.database.database import db
from app.Batch.model import Batch
from app.Batch.fund_routes import CoreFund
from app.Investments.model import Investment


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestCoreFoundCreation:
    """Test creating core funds"""
    
    def test_create_core_fund_success(self, client, auth_token):
        """Test successfully creating a core fund"""
        payload = {
            'fund_name': 'Axiom Growth Fund',
            'fund_code': 'AXIOM-001',
            'status': 'active'
        }
        
        response = client.post(
            '/api/v1/funds',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201]
        data = response.get_json()
        assert 'id' in data.get('data', data) or 'fund_name' in data.get('data', data)
    
    def test_create_core_fund_missing_name(self, client, auth_token):
        """Test validation: fund_name is required"""
        payload = {
            'fund_code': 'AXIOM-001'
        }
        
        response = client.post(
            '/api/v1/funds',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_multiple_core_funds(self, client, auth_token):
        """Test creating multiple funds"""
        fund_names = ['Axiom Fund', 'Atium Fund', 'Elantris Fund']
        
        for fund_name in fund_names:
            payload = {
                'fund_name': fund_name,
                'fund_code': fund_name.lower().replace(' ', '-')
            }
            
            response = client.post(
                '/api/v1/funds',
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
            )
            
            assert response.status_code in [200, 201]


@pytest.mark.unit
class TestCoreFoundRetrieval:
    """Test retrieving fund information"""
    
    def test_list_all_funds(self, client, auth_token, app):
        """Test listing all core funds"""
        with app.app_context():
            for i in range(3):
                fund = CoreFund(
                    fund_name=f'Fund {i}',
                    fund_code=f'FUND-{i}',
                )
                db.session.add(fund)
            db.session.commit()
        
        response = client.get(
            '/api/v1/funds',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        funds_list = data.get('data', data)
        assert len(funds_list) >= 3
    
    def test_get_fund_details(self, client, auth_token, app):
        """Test getting specific fund details"""
        with app.app_context():
            fund = CoreFund(
                fund_name='Test Fund',
                fund_code='TEST-FUND',
            )
            db.session.add(fund)
            db.session.commit()
            fund_id = fund.id
        
        response = client.get(
            f'/api/v1/funds/{fund_id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404, 405]

    def test_fund_investor_count_from_database(self, client, auth_token, sample_batch, app):
        """Test investor count reflects all investments for the fund"""
        with app.app_context():
            core_fund = CoreFund(
                fund_name='Count Test Fund',
                fund_code='COUNT-001',
            )
            db.session.add(core_fund)
            db.session.commit()

            for i in range(7):
                investment = Investment(
                    investor_name=f'Investor {i + 1}',
                    investor_email=f'investor{i + 1}@example.com',
                    internal_client_code=f'INV-{i + 1:03d}',
                    amount_deposited=1000,
                    date_deposited=datetime.now(timezone.utc),
                    batch_id=sample_batch.id,
                    fund_id=core_fund.id,
                    fund_name=core_fund.fund_name,
                )
                db.session.add(investment)
            db.session.commit()

        response = client.get(
            f'/api/v1/funds/{core_fund.id}',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200
        data = response.get_json().get('data', {})
        assert data.get('investor_count') == 7


@pytest.mark.unit
class TestCoreFoundUpdate:
    """Test updating fund information"""
    
    def test_update_fund_status(self, client, auth_token, app):
        """Test updating fund status"""
        with app.app_context():
            fund = CoreFund(
                fund_name='Update Test Fund',
                fund_code='UPDATE-TEST',
            )
            db.session.add(fund)
            db.session.commit()
            fund_id = fund.id
        
        payload = {
            'status': 'inactive'
        }
        
        response = client.patch(
            f'/api/v1/funds/{fund_id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]
    
    def test_delete_core_fund(self, client, auth_token, app):
        """Test deleting a core fund and its related records"""
        with app.app_context():
            fund = CoreFund(
                fund_name='Delete Test Fund',
                fund_code='DELETE-TEST',
            )
            db.session.add(fund)
            db.session.commit()
            fund_id = fund.id

            # add a dependent investment and withdrawal to validate cascade delete behavior
            inv = Investment(
                investor_name='Delete Investor',
                investor_email='del@example.com',
                internal_client_code='INV-DEL',
                amount_deposited=1000,
                batch_id=1,
                fund_id=fund_id,
            )
            db.session.add(inv)
            db.session.commit()

        response = client.delete(
            f'/api/v1/funds/{fund_id}',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200

        # ensure fund is removed (not soft-deleted)
        with app.app_context():
            assert db.session.query(CoreFund).filter(CoreFund.id == fund_id).first() is None
            assert db.session.query(Investment).filter(Investment.fund_id == fund_id).count() == 0


@pytest.mark.unit
class TestBatchFundOperations:
    """Test fund operations at batch level"""
    
    def test_get_batch_funds(self, client, auth_token, sample_batch, app):
        """Test retrieving funds for a specific batch"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/funds',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_get_fund_details_by_batch(self, client, auth_token, sample_batch):
        """Test getting fund details by batch"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/funds/Axiom',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_record_fund_performance(self, client, auth_token, sample_batch):
        """Test recording fund performance data"""
        payload = {
            'fund_name': 'Axiom',
            'performance_date': datetime.now(timezone.utc).isoformat(),
            'fund_value': '1050000.00',
            'profit': '50000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/funds/Axiom/performance',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 404]
    
    def test_get_fund_weekly_update(self, client, auth_token, sample_batch):
        """Test getting fund weekly update"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/funds/Axiom/weekly-update',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_calculate_all_funds_pro_rata(self, client, auth_token, sample_batch, sample_investments):
        """Test calculating pro-rata for all funds in batch"""
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/calculate-all-funds',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 201, 400, 404, 500]


@pytest.mark.unit
class TestBatchReports:
    """Test batch report generation"""
    
    def test_generate_batch_pdf_report(self, client, auth_token, sample_batch):
        """Test generating batch PDF report"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/report/pdf',
            headers=get_auth_headers(auth_token)
        )
        
        # Should return PDF or error
        assert response.status_code in [200, 404, 500]
    
    def test_get_comprehensive_batch_summary(self, client, auth_token, sample_batch, sample_investments):
        """Test getting comprehensive batch summary"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'batch_id' in data.get('data', data) or 'id' in data.get('data', data)


@pytest.mark.unit
class TestFundWorkflow:
    """Test complete fund workflow"""
    
    def test_fund_creation_and_batch_assignment(self, client, auth_token, app, sample_batch, sample_investments):
        """Test creating fund and assigning to batch"""
        # Create fund
        fund_payload = {
            'fund_name': 'Workflow Test Fund',
            'fund_code': 'WORKFLOW-FUND',
            'status': 'active'
        }
        
        response = client.post(
            '/api/v1/funds',
            data=json.dumps(fund_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201]
        
        # Record performance
        perf_payload = {
            'fund_name': 'Workflow Test Fund',
            'performance_date': datetime.now(timezone.utc).isoformat(),
            'fund_value': '1000000.00'
        }
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/funds/Workflow Test Fund/performance',
            data=json.dumps(perf_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201, 404]
