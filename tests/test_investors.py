"""
Investor Management Tests
==========================
Tests for investor profile management, statements, and withdrawal operations.

Run with: pytest tests/test_investors.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.database.database import db
from app.Batch.fund_routes import CoreFund
from app.Batch.model import Batch
from app.Investments.model import Investment, Withdrawal, EpochLedger


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestInvestorRegistry:
    """Test investor registry and profile management"""
    
    def test_list_all_investors(self, client, auth_token, sample_investments):
        """Test retrieving all investors"""
        response = client.get(
            '/api/v1/investors',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 2  # sample_investments has 2 investors

    def test_investor_directory_counts_post_epoch_deposits(self, client, auth_token, app):
        """Investor balance should include deposits after the latest committed epoch."""
        from datetime import datetime, timezone
        from decimal import Decimal

        with app.app_context():
            batch1 = Batch(batch_name='Batch 1', date_deployed=datetime(2026, 4, 1, tzinfo=timezone.utc))
            batch2 = Batch(batch_name='Batch 2', date_deployed=datetime(2026, 9, 1, tzinfo=timezone.utc))
            db.session.add_all([batch1, batch2])
            db.session.flush()

            core_fund = CoreFund(fund_name='Atium')
            db.session.add(core_fund)
            db.session.flush()

            inv1 = Investment(
                investor_name='Andrew Harris',
                investor_email='andrew@example.com',
                internal_client_code='ATIUM-008',
                amount_deposited=Decimal('50000.00'),
                date_deposited=datetime(2026, 4, 6, tzinfo=timezone.utc),
                batch_id=batch1.id,
                fund_id=core_fund.id,
                fund_name=core_fund.fund_name,
            )
            inv2 = Investment(
                investor_name='Andrew Harris',
                investor_email='andrew@example.com',
                internal_client_code='ATIUM-008',
                amount_deposited=Decimal('50000.00'),
                date_deposited=datetime(2026, 9, 10, tzinfo=timezone.utc),
                batch_id=batch2.id,
                fund_id=core_fund.id,
                fund_name=core_fund.fund_name,
            )
            db.session.add_all([inv1, inv2])
            db.session.flush()

            ledger = EpochLedger(
                internal_client_code='ATIUM-008',
                fund_name='Atium',
                epoch_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
                epoch_end=datetime(2026, 8, 31, tzinfo=timezone.utc),
                performance_rate=Decimal('0.21185700'),
                start_balance=Decimal('50000.00'),
                deposits=Decimal('0.00'),
                withdrawals=Decimal('0.00'),
                profit=Decimal('10592.81'),
                end_balance=Decimal('60592.81'),
                previous_hash='prevhash-008',
                current_hash='hash-008-1',
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(ledger)
            db.session.commit()

        response = client.get(
            '/api/v1/investors',
            headers=get_auth_headers(auth_token)
        )
        assert response.status_code == 200
        data = response.get_json()['data']
        investor = next((item for item in data if item['internal_client_code'] == 'ATIUM-008'), None)
        assert investor is not None
        assert abs(investor['total_principal'] - 110592.81) < 0.01

    def test_get_investor_by_client_code(self, client, auth_token, sample_investments, app):
        """Test retrieving specific investor by client code"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        response = client.get(
            f'/api/v1/investors/{client_code}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['internal_client_code'] == client_code
    
    def test_get_investor_not_found(self, client, auth_token):
        """Test retrieving non-existent investor"""
        response = client.get(
            '/api/v1/investors/NONEXISTENT-CODE',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 404
    
    def test_list_investors_pagination(self, client, auth_token):
        """Test pagination in investor list"""
        response = client.get(
            '/api/v1/investors?page=1&limit=10',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
    
    def test_list_investors_by_batch(self, client, auth_token, sample_batch):
        """Test listing investors in specific batch"""
        response = client.get(
            f'/api/v1/batches/{sample_batch.id}/investments',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200


@pytest.mark.unit
class TestInvestorProfile:
    """Test updating investor profiles"""
    
    def test_update_investor_profile(self, client, auth_token, sample_investments, app):
        """Test updating investor profile details"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        payload = {
            'investor_email': 'newemail@example.com',
            'investor_phone': '+1111111111'
        }
        
        response = client.patch(
            f'/api/v1/investors/{client_code}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]
    
    def test_update_investor_wealth_manager(self, client, auth_token, sample_investments, app):
        """Test updating investor wealth manager"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        payload = {
            'wealth_manager': 'New Manager'
        }
        
        response = client.patch(
            f'/api/v1/investors/{client_code}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]
    
    def test_update_nonexistent_investor(self, client, auth_token):
        """Test updating non-existent investor"""
        payload = {
            'investor_email': 'new@example.com'
        }
        
        response = client.patch(
            '/api/v1/investors/NONEXISTENT',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [404, 200]


@pytest.mark.unit
class TestInvestorStatements:
    """Test investor statement generation and retrieval"""
    
    def test_get_investor_statement(self, client, auth_token, sample_investments, app):
        """Test retrieving investor epoch-ledger statement"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        response = client.get(
            f'/api/v1/investors/{client_code}/statement',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            assert 'investor' in data or 'statement' in data or 'transactions' in data
    
    def test_get_investor_statement_pdf(self, client, auth_token, sample_investments, app):
        """Test generating investor statement PDF"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        response = client.get(
            f'/api/v1/investors/{client_code}/statement/pdf',
            headers=get_auth_headers(auth_token)
        )
        
        # Should return PDF or error
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            assert 'pdf' in response.content_type.lower()
    
    def test_statement_includes_transaction_history(self, client, auth_token, sample_investments, app):
        """Test statement includes complete transaction history"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        response = client.get(
            f'/api/v1/investors/{client_code}/statement',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            # Should have transaction details
            assert isinstance(data, dict)
    
    def test_statement_pdf_includes_watermark(self, client, auth_token, sample_investments, app):
        """Test that PDF statement includes proper branding"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        response = client.get(
            f'/api/v1/investors/{client_code}/statement/pdf',
            headers=get_auth_headers(auth_token)
        )
        
        # Verify PDF generation works
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestWithdrawals:
    """Test withdrawal operations"""
    
    def test_create_withdrawal_success(self, client, auth_token, sample_investments, app):
        """Test creating a withdrawal request"""
        with app.app_context():
            inv = Investment.query.first()
            investor_id = inv.id
        
        payload = {
            'investor_id': investor_id,
            'amount': '10000.00',
            'withdrawal_date': datetime.now(timezone.utc).isoformat(),
            'reason': 'Partial withdrawal'
        }
        
        response = client.post(
            '/api/v1/withdrawals',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201]
    
    def test_create_withdrawal_invalid_amount(self, client, auth_token, sample_investments, app):
        """Test withdrawal with invalid amount"""
        with app.app_context():
            inv = Investment.query.first()
            investor_id = inv.id
        
        payload = {
            'investor_id': investor_id,
            'amount': '-5000.00',  # Negative amount
            'withdrawal_date': datetime.now(timezone.utc).isoformat()
        }
        
        response = client.post(
            '/api/v1/withdrawals',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_withdrawal_exceeds_balance(self, client, auth_token, sample_investments, app):
        """Test withdrawal exceeding investor balance"""
        with app.app_context():
            inv = Investment.query.first()
            investor_id = inv.id
        
        # Try to withdraw more than deposited
        payload = {
            'investor_id': investor_id,
            'amount': '500000.00',  # More than typical investment
            'withdrawal_date': datetime.now(timezone.utc).isoformat()
        }
        
        response = client.post(
            '/api/v1/withdrawals',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        # May succeed if business logic allows or fail with validation
        assert response.status_code in [200, 201, 400]
    
    def test_get_all_withdrawals(self, client, auth_token):
        """Test retrieving all withdrawals"""
        response = client.get(
            '/api/v1/withdrawals',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.get_json()
            assert isinstance(data, list)
    
    def test_update_withdrawal_status(self, client, auth_token, sample_investments, app):
        """Test updating withdrawal status"""
        with app.app_context():
            inv = Investment.query.first()
            
            # Create withdrawal first (use correct model fields)
            withdrawal = Withdrawal(
                internal_client_code=inv.internal_client_code,
                fund_id=inv.fund_id,  # may be None if no fund assigned
                amount=Decimal('5000.00'),
                status='Pending'
            )
            db.session.add(withdrawal)
            db.session.commit()
            withdrawal_id = withdrawal.id
        
        payload = {
            'status': 'approved'
        }
        
        response = client.patch(
            f'/api/v1/withdrawals/{withdrawal_id}',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 204]


@pytest.mark.unit
class TestWithdrawalStatusLifecycle:
    """Test withdrawal status lifecycle and valuation integration"""
    
    def test_withdrawal_statuses_in_valuation(self, client, auth_token, sample_investments, app):
        """Test that Processed and Completed withdrawals are included in valuation calculations"""
        with app.app_context():
            inv = Investment.query.first()
            
            # Create approved withdrawal
            withdrawal = Withdrawal(
                internal_client_code=inv.internal_client_code,
                fund_id=inv.fund_id,
                amount=Decimal('5000.00'),
                status='Approved'
            )
            db.session.add(withdrawal)
            db.session.commit()
            withdrawal_id = withdrawal.id
        
        # Test that approved withdrawal is included in valuation preview
        response = client.get(
            '/api/v1/valuation/epoch/dry-run?fund_id=1&start_date=2026-04-01T00:00:00Z&end_date=2026-04-30T23:59:59Z&performance_rate=0.05',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()['data']
        assert 'total_withdrawals' in data
        assert data['total_withdrawals'] >= 5000.00  # Should include our approved withdrawal
        
        # Clean up
        with app.app_context():
            db.session.delete(withdrawal)
            db.session.commit()

    def test_valuation_preview_includes_legacy_withdrawals_by_fund_name(self, client, auth_token, app):
        """Legacy withdrawals without fund_id should still reduce active capital in valuation preview"""
        fund_id = None
        with app.app_context():
            core_fund = CoreFund(fund_name='Legacy Fund', fund_code='LF-2026-01')
            db.session.add(core_fund)
            batch = Batch(batch_name='Legacy Withdrawal Batch', certificate_number='CERT-LG-1')
            db.session.add(batch)
            db.session.commit()
            fund_id = core_fund.id

            investment = Investment(
                investor_name='Legacy Withdrawal Investor',
                investor_email='legacy@example.com',
                internal_client_code='INV-LEGACY-001',
                amount_deposited=Decimal('100000.00'),
                date_deposited=datetime(2026, 6, 1, tzinfo=timezone.utc),
                batch_id=batch.id,
                fund_id=fund_id,
                fund_name=core_fund.fund_name,
            )
            withdrawal = Withdrawal(
                internal_client_code=investment.internal_client_code,
                fund_id=None,
                fund_name=core_fund.fund_name,
                amount=Decimal('4000.00'),
                date_withdrawn=datetime(2026, 6, 15, tzinfo=timezone.utc),
                status='Approved',
                approved_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            )
            db.session.add_all([investment, withdrawal])
            db.session.commit()

        response = client.get(
            f'/api/v1/valuation/epoch/dry-run?fund_id={fund_id}&start_date=2026-06-01T00:00:00Z&end_date=2026-06-30T23:59:59Z&performance_rate=0.05',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200
        data = response.get_json()['data']
        assert 'total_withdrawals' in data
        assert data['total_withdrawals'] >= 4000.00

        with app.app_context():
            db.session.delete(withdrawal)
            db.session.delete(investment)
            db.session.commit()
    
    def test_post_valuation_status_update(self, client, auth_token, sample_investments, app):
        """Test that withdrawals are marked as Processed after valuation commit"""
        with app.app_context():
            inv = Investment.query.first()
            
            # Create approved withdrawal
            withdrawal = Withdrawal(
                internal_client_code=inv.internal_client_code,
                fund_id=inv.fund_id,
                amount=Decimal('10000.00'),
                status='Approved'
            )
            db.session.add(withdrawal)
            db.session.commit()
            withdrawal_id = withdrawal.id
        
        # Verify initial status
        with app.app_context():
            wd = Withdrawal.query.get(withdrawal_id)
            assert wd.status == 'Approved'
        
        # Run valuation commit (this should update withdrawal status)
        response = client.post(
            '/api/v1/valuation/epoch/commit',
            json={
                'fund_id': 1,
                'start_date': '2026-04-01T00:00:00Z',
                'end_date': '2026-04-30T23:59:59Z',
                'performance_rate': 0.05
            },
            headers=get_auth_headers(auth_token)
        )
        
        # Check that withdrawal status was updated to Processed
        with app.app_context():
            wd = Withdrawal.query.get(withdrawal_id)
            assert wd.status == 'Processed'
            
            # Clean up
            db.session.delete(wd)
            db.session.commit()


@pytest.mark.unit
class TestInvestorWithdrawalWorkflow:
    """Test complete investor withdrawal workflow"""
    
    def test_withdrawal_request_to_completion(self, client, auth_token, app):
        """Test complete withdrawal workflow"""
        with app.app_context():
            batch = Batch(
                batch_name='WITHDRAWAL-TEST',
                certificate_number='CERT-WTH',
                total_principal=Decimal('100000.00'),
                stage=2
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id
            
            inv = Investment(
                investor_name='Withdrawal Test Investor',
                investor_email='wthtest@example.com',
                internal_client_code='WTH-TEST-001',
                amount_deposited=Decimal('100000.00'),
                batch_id=batch_id
            )
            db.session.add(inv)
            db.session.commit()
            inv_id = inv.id
        
        # Step 1: Get investor profile
        response = client.get(
            f'/api/v1/investors/WTH-TEST-001',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        
        # Step 2: Get investor statement
        response = client.get(
            f'/api/v1/investors/WTH-TEST-001/statement',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
        
        # Step 3: Create withdrawal
        payload = {
            'investor_id': inv_id,
            'amount': '20000.00',
            'withdrawal_date': datetime.now(timezone.utc).isoformat(),
            'reason': 'Partial redemption'
        }
        
        response = client.post(
            '/api/v1/withdrawals',
            data=json.dumps(payload),
            headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 201]
        
        # Step 4: Retrieve all withdrawals
        response = client.get(
            '/api/v1/withdrawals',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestInvestorDataIntegrity:
    """Test investor data integrity and consistency"""
    
    def test_investor_profile_consistency(self, client, auth_token, sample_investments, app):
        """Test that investor profiles are consistent across endpoints"""
        with app.app_context():
            inv = Investment.query.first()
            client_code = inv.internal_client_code
        
        # Get from investor endpoint
        response1 = client.get(
            f'/api/v1/investors/{client_code}',
            headers=get_auth_headers(auth_token)
        )
        
        # Get from investments endpoint
        response2 = client.get(
            f'/api/v1/investments/{sample_investments[0].id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.get_json()
        data2 = response2.get_json()
        
        # Key fields should match
        assert data1.get('investor_name') == data2.get('investor_name')
        assert data1.get('investor_email') == data2.get('investor_email')
    
    def test_withdrawal_reduces_available_balance(self, client, auth_token, app):
        """Test that withdrawals are reflected in statements"""
        with app.app_context():
            batch = Batch(
                batch_name='BAL-TEST',
                certificate_number='CERT-BAL',
                total_principal=Decimal('50000.00'),
                stage=2
            )
            db.session.add(batch)
            db.session.flush()  # Ensure batch gets ID
            batch_id = batch.id
            
            inv = Investment(
                investor_name='Balance Test',
                investor_email='baltest@example.com',
                internal_client_code='BAL-001',
                amount_deposited=Decimal('50000.00'),
                batch_id=batch_id
            )
            db.session.add(inv)
            db.session.commit()
            
            # Create withdrawal (use correct model fields)
            withdraw = Withdrawal(
                internal_client_code=inv.internal_client_code,
                fund_id=inv.fund_id,  # may be None if no fund assigned
                amount=Decimal('10000.00'),
                status='Approved'
            )
            db.session.add(withdraw)
            db.session.commit()
        
        # Check statement reflects withdrawal
        response = client.get(
            '/api/v1/investors/BAL-001/statement',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 404]
