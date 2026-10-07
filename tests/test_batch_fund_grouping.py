"""
Test for fund-based grouping in batch detail API
Tests that investments are correctly grouped by fund name
"""

import pytest
import json
from datetime import datetime
from decimal import Decimal
from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.Batch.core_fund import CoreFund


@pytest.mark.unit
class TestBatchDetailFundGrouping:
    """Test fund-based grouping in batch detail API response"""

    def test_batch_detail_includes_grouped_by_fund(self, client, auth_token, setup_batch_with_investments):
        """Test that batch detail response includes grouped_by_fund structure"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        
        # Verify grouped_by_fund exists
        assert 'grouped_by_fund' in data
        assert isinstance(data['grouped_by_fund'], dict)
        assert len(data['grouped_by_fund']) > 0

    def test_grouped_by_fund_structure(self, client, auth_token, setup_batch_with_investments):
        """Test that grouped_by_fund has correct structure"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        grouped = data['grouped_by_fund']
        
        # Each fund should have required fields
        for fund_name, fund_data in grouped.items():
            assert isinstance(fund_name, str)
            assert 'fund_id' in fund_data
            assert 'fund_name' in fund_data
            assert 'investor_count' in fund_data
            assert 'total_principal' in fund_data
            assert 'investors' in fund_data
            assert isinstance(fund_data['investors'], list)

    def test_grouped_by_fund_investor_count(self, client, auth_token, setup_batch_with_investments):
        """Test that investor_count matches actual investor list length"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        grouped = data['grouped_by_fund']
        
        for fund_name, fund_data in grouped.items():
            expected_count = len(fund_data['investors'])
            assert fund_data['investor_count'] == expected_count, \
                f"Fund {fund_name}: expected {expected_count}, got {fund_data['investor_count']}"

    def test_grouped_by_fund_total_principal(self, client, auth_token, setup_batch_with_investments):
        """Test that total_principal matches sum of investor amounts"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        grouped = data['grouped_by_fund']
        
        for fund_name, fund_data in grouped.items():
            expected_total = sum(inv['amount_deposited'] for inv in fund_data['investors'])
            assert abs(fund_data['total_principal'] - expected_total) < 0.01, \
                f"Fund {fund_name}: expected {expected_total}, got {fund_data['total_principal']}"

    def test_grouped_by_fund_investor_structure(self, client, auth_token, setup_batch_with_investments):
        """Test that each investor in grouped data has correct structure"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        grouped = data['grouped_by_fund']
        
        for fund_name, fund_data in grouped.items():
            for investor in fund_data['investors']:
                # Each investor should have these fields
                assert 'id' in investor
                assert 'investor_name' in investor
                assert 'internal_client_code' in investor
                assert 'amount_deposited' in investor
                assert 'fund_id' in investor
                assert 'fund_name' in investor
                assert investor['fund_name'] == fund_name

    def test_grouped_by_fund_matches_flat_investments(self, client, auth_token, setup_batch_with_investments):
        """Test that grouped_by_fund reconciles with flat investments array"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        
        # Count total investors in grouped structure
        grouped_total = sum(
            len(fund_data['investors']) 
            for fund_data in data['grouped_by_fund'].values()
        )
        
        # Should match flat investments array
        flat_total = len(data['investments'])
        assert grouped_total == flat_total == data['investment_rows_count']

    def test_batch_with_single_fund(self, client, auth_token, reset_db):
        """Test grouping with only one fund"""
        from app.database.database import db
        # Create batch and fund
        session = db.session
        batch = Batch(
            batch_name="Single-Fund-Batch",
            date_created=datetime.now(),
            certificate_number="SINGLE-001",
            duration_days=365
        )
        session.add(batch)
        session.flush()
        batch_id = batch.id
        
        fund = CoreFund(fund_name="SingleFund")
        session.add(fund)
        session.flush()
        
        # Add two investors to same fund
        for i in range(2):
            inv = Investment(
                batch_id=batch_id,
                investor_name=f"Investor {i+1}",
                investor_email="test@example.com",
                internal_client_code=f"CODE-{i+1}",
                amount_deposited=Decimal('10000.00'),
                fund_id=fund.id,
                fund_name=fund.fund_name,
                date_deposited=datetime.now()
            )
            session.add(inv)
        
        session.commit()
        
        # Get batch detail
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        grouped = data['grouped_by_fund']
        
        # Should have exactly one fund in grouped structure
        assert len(grouped) == 1
        assert 'SingleFund' in grouped
        assert grouped['SingleFund']['investor_count'] == 2
        assert grouped['SingleFund']['total_principal'] == 20000.00
        
        # Cleanup
        session.delete(batch)
        session.commit()

    def test_batch_with_multiple_funds_multiple_investors(self, client, auth_token, reset_db):
        """Test grouping with multiple funds and multiple investors"""
        from app.database.database import db
        session = db.session
        batch = Batch(
            batch_name="Multi-Fund-Multi-Investor",
            date_created=datetime.now(),
            certificate_number="MULTI-001",
            duration_days=365
        )
        session.add(batch)
        session.flush()
        batch_id = batch.id
        
        # Create 3 funds
        fund_names = ["Fund-A", "Fund-B", "Fund-C"]
        funds = {}
        for name in fund_names:
            fund = CoreFund(fund_name=name)
            session.add(fund)
            session.flush()
            funds[name] = fund
        
        # Add 2 investors to each fund
        investor_count = 0
        for fund_name, fund in funds.items():
            for i in range(2):
                investor_count += 1
                inv = Investment(
                    batch_id=batch_id,
                    investor_name=f"Investor-{investor_count}",
                    investor_email="test@example.com",
                    internal_client_code=f"CODE-{investor_count}",
                    amount_deposited=Decimal('5000.00'),
                    fund_id=fund.id,
                    fund_name=fund.fund_name,
                    date_deposited=datetime.now()
                )
                session.add(inv)
        
        session.commit()
        
        # Get batch detail
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        grouped = data['grouped_by_fund']
        
        # Should have exactly 3 funds
        assert len(grouped) == 3
        
        # Each fund should have 2 investors with $10,000 total
        for fund_name in fund_names:
            assert fund_name in grouped
            assert grouped[fund_name]['investor_count'] == 2
            assert grouped[fund_name]['total_principal'] == 10000.00
        
        # Total should be 6 investors
        assert data['investment_rows_count'] == 6
        
        # Cleanup
        session.delete(batch)
        session.commit()

    def test_backward_compatibility_with_investments_array(self, client, auth_token, setup_batch_with_investments):
        """Test that flat investments array is still present for backward compatibility"""
        batch_id = setup_batch_with_investments['batch_id']
        
        response = client.get(
            f'/api/v1/batches/{batch_id}',
            headers={'Authorization': f'Bearer {auth_token}'}
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        
        # Both should exist
        assert 'investments' in data
        assert 'grouped_by_fund' in data
        
        # investments should be an array
        assert isinstance(data['investments'], list)
        assert len(data['investments']) > 0
        
        # Each investment should have fund_name
        for inv in data['investments']:
            assert 'fund_name' in inv


@pytest.fixture
def setup_batch_with_investments(reset_db):
    """Setup a batch with multiple investments in different funds"""
    from app.database.database import db
    session = db.session
    
    # Create batch
    batch = Batch(
        batch_name="Test-Batch-Grouping",
        date_created=datetime.now(),
        certificate_number="TEST-GROUP-001",
        duration_days=365
    )
    session.add(batch)
    session.flush()
    batch_id = batch.id
    
    # Create funds
    fund_names = ["Axiom", "Dynamic", "Global"]
    funds = {}
    for name in fund_names:
        fund = CoreFund(fund_name=name)
        session.add(fund)
        session.flush()
        funds[name] = fund
    
    # Add investments
    for fund_name, fund in funds.items():
        for i in range(2):
            inv = Investment(
                batch_id=batch_id,
                investor_name=f"{fund_name}-Investor-{i+1}",
                investor_email="test@example.com",
                internal_client_code=f"{fund_name}-CODE-{i+1}",
                amount_deposited=Decimal("5000.00"),
                fund_id=fund.id,
                fund_name=fund.fund_name,
                date_deposited=datetime.now()
            )
            session.add(inv)
    
    session.commit()
    
    yield {'batch_id': batch_id}
    
    # Cleanup
    session.delete(batch)
    session.commit()
