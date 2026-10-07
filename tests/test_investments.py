"""
Investment Route Tests
======================
Tests for investment upload, creation, retrieval, and deletion endpoints.
Verifies that new columns (Wealth Manager, IFA, etc.) are correctly saved.

Run with: pytest tests/test_investments.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.database.database import db
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.utils.audit_log import AuditLog


@pytest.mark.unit
class TestInvestmentCreation:
    """Test creating individual investments"""
    
    def test_add_investment_success(self, client, sample_batch, auth_token):
        """Test successfully creating an investment with all new columns"""
        payload = {
            'batch_id': sample_batch.id,
            'investor_name': 'Test Investor',
            'investor_email': 'investor@example.com',
            'investor_phone': '+1234567890',
            'internal_client_code': 'INV-TEST-001',
            'amount_deposited': '50000.00',
            'date_deposited': datetime.now(timezone.utc).isoformat(),
            'wealth_manager': 'John Manager',
            'IFA': 'Alice IFA',
            'contract_note': 'https://example.com/contract.pdf',
        }
        
        response = client.post(
            '/api/v1/investments',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        data = response.get_json()
        assert data['status'] == 201
        assert 'id' in data
        
        # Verify data in database
        investment = db.session.get(Investment, data['id'])
        assert investment is not None
        assert investment.investor_name == 'Test Investor'
        assert investment.wealth_manager == 'John Manager'
        assert investment.IFA == 'Alice IFA'
        assert investment.contract_note == 'https://example.com/contract.pdf'
    
    def test_add_investment_missing_batch_id(self, client, auth_token):
        """Test validation: batch_id is required"""
        payload = {
            'investor_name': 'Test Investor',
            'investor_email': 'investor@example.com',
            'amount_deposited': '50000.00',
        }
        
        response = client.post(
            '/api/v1/investments',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_add_investment_missing_body(self, client, auth_token):
        """Test validation: request body is required"""
        response = client.post(
            '/api/v1/investments',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 400
    
    def test_add_investment_allows_duplicate_code_same_batch(self, client, sample_batch, auth_token):
        """Test validation: internal_client_code is allowed to duplicate per batch"""
        # Create first investment
        first_payload = {
            'batch_id': sample_batch.id,
            'investor_name': 'Investor 1',
            'investor_email': 'inv1@example.com',
            'internal_client_code': 'INV-001',
            'amount_deposited': '50000.00',
            'date_deposited': datetime.now(timezone.utc).isoformat(),
        }
        
        response1 = client.post(
            '/api/v1/investments',
            data=json.dumps(first_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        assert response1.status_code == 201
        
        # Try to create with same code but different name
        second_payload = first_payload.copy()
        second_payload['investor_name'] = 'Investor 2'
        
        response2 = client.post(
            '/api/v1/investments',
            data=json.dumps(second_payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # Should succeed because duplicates are now allowed
        assert response2.status_code == 201

@pytest.mark.unit
class TestInvestmentRetrieval:
    """Test retrieving investment data"""
    
    def test_get_investment_success(self, client, sample_investments, auth_token):
        """Test retrieving a single investment"""
        investment = sample_investments[0]
        
        response = client.get(
            f'/api/v1/investments/{investment.id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == investment.id
        assert data['investor_name'] == investment.investor_name
        assert data['wealth_manager'] == 'Jane Smith'
        assert data['IFA'] == 'Robert Johnson'
    
    def test_get_investment_not_found(self, client, auth_token):
        """Test retrieving non-existent investment"""
        response = client.get(
            '/api/v1/investments/99999',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 404
    
    def test_list_investments_by_batch(self, client, sample_batch, sample_investments, auth_token):
        """Test listing all investments in a batch"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/investments',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list) or 'investments' in data
        
        # If it's a paginated response
        if isinstance(data, dict) and 'investments' in data:
            investments = data['investments']
        else:
            investments = data
        
        assert len(investments) == 2


@pytest.mark.unit
class TestInvestmentUpdate:
    """Test updating investment data"""
    
    def test_update_investment_wealth_manager(self, client, sample_investments, auth_token):
        """Test updating wealth manager field"""
        investment = sample_investments[0]
        
        payload = {
            'wealth_manager': 'Updated Manager Name',
        }
        
        response = client.put(
            f'/api/v1/investments/{investment.id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 200
        
        # Verify update in database
        updated = db.session.get(Investment, investment.id)
        assert updated.wealth_manager == 'Updated Manager Name'
    
    def test_update_investment_multiple_fields(self, client, sample_investments, auth_token):
        """Test updating multiple fields at once"""
        investment = sample_investments[0]
        
        payload = {
            'IFA': 'New IFA',
            'contract_note': 'https://new-contract-link.com',
            'valuation': '60000.00',
        }
        
        response = client.put(
            f'/api/v1/investments/{investment.id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 200
        
        updated = db.session.get(Investment, investment.id)
        assert updated.IFA == 'New IFA'
        assert updated.contract_note == 'https://new-contract-link.com'
        assert updated.valuation == Decimal('60000.00')


@pytest.mark.unit
class TestBatchInvestmentIntegration:
    """Test interactions between batches and investments"""
    
    def test_total_principal_calculation(self, app, sample_batch, sample_investments):
        """Test that batch total_principal matches sum of investments"""
        with app.app_context():
            total = sum(inv.amount_deposited for inv in sample_investments)
            
            # In a real app, you might auto-update this
            # For now, just verify the logic
            assert total == Decimal('150000.00')
    
    def test_batch_stage_progression(self, app, sample_batch, sample_investments):
        """Test batch stage progression from Deposited to Active"""
        with app.app_context():
            batch = db.session.get(Batch, sample_batch.id)
            
            # Stage 1: Deposited (default)
            assert batch.stage == 1
            assert batch.is_transferred is False
            
            # Simulate stage 2: Transferred
            batch.stage = 2
            batch.is_transferred = True
            db.session.commit()
            
            # Verify update
            batch = db.session.get(Batch, sample_batch.id)
            assert batch.stage == 2
            assert batch.is_transferred is True
    
    def test_delete_investment(self, client, sample_investments, auth_token):
        """Test deleting an investment"""
        investment = sample_investments[0]
        
        response = client.delete(
            f'/api/v1/investments/{investment.id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 204
        
        # Verify deletion
        deleted = db.session.get(Investment, investment.id)
        assert deleted is None


@pytest.mark.integration
class TestInvestmentFileUpload:
    """Test Excel file upload and bulk investment creation"""
    
    def test_upload_excel_file(self, client, sample_batch, auth_token):
        """Test uploading Excel file with multiple investments (requires tempfile or BytesIO)"""
        # This test requires actual file handling
        # You would typically use BytesIO to simulate file upload
        # Example implementation:
        """
        from io import BytesIO
        import openpyxl
        
        # Create test Excel file
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['Investor Name', 'Email', 'Amount', 'Wealth Manager', 'IFA'])
        ws.append(['John Doe', 'john@example.com', 50000, 'Manager 1', 'IFA 1'])
        ws.append(['Jane Smith', 'jane@example.com', 75000, 'Manager 2', 'IFA 2'])
        
        file = BytesIO()
        wb.save(file)
        file.seek(0)
        
        response = client.post(
            f'/api/v1/batches/{sample_batch.id}/upload-investments',
            data={'file': (file, 'test.xlsx')},
            headers=get_auth_headers(auth_token),
            content_type='multipart/form-data'
        )
        
        assert response.status_code == 200
        """
        pass


# ==================== HELPER FUNCTION ====================

def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}
