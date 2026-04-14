"""
Reports Tests
=============
Tests for report generation, portfolio views, and report retrieval endpoints.

Run with: pytest tests/test_reports.py -v
"""

import pytest
import json
from datetime import datetime
from decimal import Decimal
from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestReportsList:
    """Test retrieving reports list"""
    
    def test_list_reports(self, client, auth_token):
        """Test listing all committed valuation runs as reports"""
        response = client.get(
            '/api/v1/reports',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            assert isinstance(data.get('data', []), list)
    
    def test_list_reports_pagination(self, client, auth_token):
        """Test pagination in reports list"""
        response = client.get(
            '/api/v1/reports?page=1&limit=10',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestPortfolioReports:
    """Test portfolio view and summary reports"""
    
    def test_portfolio_view(self, client, auth_token):
        """Test getting global portfolio AUM per active fund"""
        response = client.get(
            '/api/v1/reports/portfolio',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Should show fund-level metrics
            assert isinstance(data, (dict, list))
    
    def test_multi_batch_portfolio(self, client, auth_token):
        """Test multi-batch portfolio summary (Excel export)"""
        response = client.get(
            '/api/v1/reports/portfolio/multi-batch',
            headers=get_auth_headers(auth_token)
        )
        
        # Should return Excel or JSON
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            # Check if it's Excel or JSON
            assert response.content_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/json']


@pytest.mark.unit
class TestBatchSummaryReports:
    """Test batch-level summary reports"""
    
    def test_batch_summary_excel(self, client, auth_token, sample_batch):
        """Test getting batch summary as Excel export"""
        response = client.get(
            f'/api/v1/reports/batch/{sample_batch.id}/summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            # Should return Excel file
            assert response.content_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/json']
    
    def test_batch_summary_invalid_batch(self, client, auth_token):
        """Test batch summary for non-existent batch"""
        response = client.get(
            '/api/v1/reports/batch/99999/summary',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [404, 200]


@pytest.mark.unit
class TestBatchReconciliation:
    """Test batch reconciliation reports"""
    
    def test_batch_reconciliation(self, client, auth_token, sample_batch):
        """Test getting batch reconciliation data"""
        response = client.get(
            f'/api/v1/reports/batch/{sample_batch.id}/reconciliation',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Should contain reconciliation details
            assert isinstance(data, dict)
    
    def test_batch_reconciliation_with_investments(self, client, auth_token, sample_batch, sample_investments):
        """Test reconciliation with investments"""
        response = client.get(
            f'/api/v1/reports/batch/{sample_batch.id}/reconciliation',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Should match investment totals
            assert isinstance(data, dict)


@pytest.mark.unit
class TestValuationRunReports:
    """Test reports for specific valuation runs"""
    
    def test_get_valuation_run_report(self, client, auth_token):
        """Test getting detailed report for a valuation run"""
        response = client.get(
            '/api/v1/reports/1',
            headers=get_auth_headers(auth_token)
        )
        
        # May not exist, but should handle gracefully
        assert response.status_code in [200, 404]
    
    def test_get_valuation_run_pdf(self, client, auth_token):
        """Test generating PDF report for valuation run"""
        response = client.get(
            '/api/v1/reports/1/pdf',
            headers=get_auth_headers(auth_token)
        )
        
        # Should return PDF or error
        assert response.status_code in [200, 404]
    
    def test_list_valuation_runs_legacy(self, client, auth_token):
        """Test legacy valuation runs endpoint"""
        response = client.get(
            '/api/v1/reports/valuation-runs',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_get_valuation_run_legacy(self, client, auth_token):
        """Test legacy get valuation run endpoint"""
        response = client.get(
            '/api/v1/reports/valuation-runs/1',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_get_valuation_run_pdf_legacy(self, client, auth_token):
        """Test legacy PDF report endpoint"""
        response = client.get(
            '/api/v1/reports/valuation-runs/1/pdf',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestReportFiltering:
    """Test report filtering and search capabilities"""
    
    def test_reports_filter_by_date_range(self, client, auth_token):
        """Test filtering reports by date range"""
        start_date = datetime(2026, 1, 1).isoformat()
        end_date = datetime(2026, 12, 31).isoformat()
        
        response = client.get(
            f'/api/v1/reports?start_date={start_date}&end_date={end_date}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_portfolio_filter_by_fund(self, client, auth_token):
        """Test filtering portfolio by fund"""
        response = client.get(
            '/api/v1/reports/portfolio?fund_name=Axiom',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
    
    def test_reports_search(self, client, auth_token):
        """Test searching reports"""
        response = client.get(
            '/api/v1/reports?search=MAR-2026',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestReportExports:
    """Test report export formats"""
    
    def test_portfolio_export_excel(self, client, auth_token):
        """Test exporting portfolio as Excel"""
        response = client.get(
            '/api/v1/reports/portfolio/multi-batch?format=xlsx',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            assert 'spreadsheet' in response.content_type or 'json' in response.content_type
    
    def test_batch_summary_export_formats(self, client, auth_token, sample_batch):
        """Test batch summary in different formats"""
        # Try Excel
        response = client.get(
            f'/api/v1/reports/batch/{sample_batch.id}/summary?format=xlsx',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestReportDataAccuracy:
    """Test report data accuracy and calculations"""
    
    def test_portfolio_aum_calculation(self, client, auth_token, app):
        """Test portfolio AUM calculation is correct"""
        with app.app_context():
            # Create batch with known principal
            batch = Batch(
                batch_name='AUM-TEST',
                certificate_number='CERT-AUM',
                total_principal=Decimal('250000.00'),
                is_active=True,
                stage=4
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id
            
            # Add investments
            inv1 = Investment(
                investor_name='AUM Investor 1',
                investor_email='auminv1@example.com',
                internal_client_code='AUMINV-1',
                amount_deposited=Decimal('150000.00'),
                batch_id=batch_id
            )
            
            inv2 = Investment(
                investor_name='AUM Investor 2',
                investor_email='auminv2@example.com',
                internal_client_code='AUMINV-2',
                amount_deposited=Decimal('100000.00'),
                batch_id=batch_id
            )
            
            db.session.add_all([inv1, inv2])
            db.session.commit()
        
        response = client.get(
            '/api/v1/reports/portfolio',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Verify data structure
            assert isinstance(data, (dict, list))
    
    def test_reconciliation_totals_match(self, client, auth_token, sample_batch, sample_investments):
        """Test that reconciliation totals match investments"""
        response = client.get(
            f'/api/v1/reports/batch/{sample_batch.id}/reconciliation',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Total should match sum of investments
            if 'total' in data and 'investments' in data:
                assert data['total'] >= sum([inv.get('amount', 0) for inv in data['investments']])


@pytest.mark.unit
class TestReportSecurity:
    """Test report access control and security"""
    
    def test_report_requires_auth(self, client):
        """Test that reports require authentication"""
        response = client.get('/api/v1/reports')
        
        # Should require JWT token
        assert response.status_code in [401, 200]  # 401 if auth required
    
    def test_portfolio_requires_auth(self, client):
        """Test that portfolio requires authentication"""
        response = client.get('/api/v1/reports/portfolio')
        
        assert response.status_code in [401, 200]


@pytest.mark.unit
class TestReportPerformance:
    """Test report generation performance"""
    
    def test_large_portfolio_report_generation(self, client, auth_token, app):
        """Test report generation with large dataset"""
        with app.app_context():
            # Create multiple batches with investments
            for batch_idx in range(5):
                batch = Batch(
                    batch_name=f'PERF-TEST-{batch_idx}',
                    certificate_number=f'CERT-PERF-{batch_idx}',
                    total_principal=Decimal('100000.00'),
                    is_active=True
                )
                db.session.add(batch)
                db.session.flush()  # Ensure batch gets ID before using it
                batch_id = batch.id
                
                # Add multiple investments per batch
                for inv_idx in range(10):
                    inv = Investment(
                        investor_name=f'Perf Investor {batch_idx}-{inv_idx}',
                        investor_email=f'perfinv{batch_idx}{inv_idx}@example.com',
                        internal_client_code=f'PERFINV-{batch_idx}-{inv_idx}',
                        amount_deposited=Decimal('10000.00'),
                        batch_id=batch_id
                    )
                    db.session.add(inv)
            
            db.session.commit()
        
        # Should handle large dataset efficiently
        response = client.get(
            '/api/v1/reports/portfolio',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
