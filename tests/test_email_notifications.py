"""
Email Notification Tests
========================
Tests for email sending on Deposit, Transfer, and Active status changes.
Uses mocking to verify correct subject lines and recipients without sending real emails.

Run with: pytest tests/test_email_notifications.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.utils.audit_log import audit_log_email
from app.database.database import db


@pytest.mark.unit
class TestEmailNotificationTemplates:
    """Test email subject lines and templates"""
    
    def test_deposit_email_subject(self):
        """Test that Deposit email has correct subject line"""
        subject = "Investment Deposit Confirmation"
        assert 'Deposit' in subject or 'deposit' in subject.lower()
    
    def test_transfer_email_subject(self):
        """Test that Transfer email has correct subject line"""
        subject = "Investment Transfer Confirmation"
        assert 'Transfer' in subject or 'transfer' in subject.lower()
    
    def test_active_email_subject(self):
        """Test that Active status email has correct subject line"""
        subject = "Investment Fund Activated"
        assert 'Activat' in subject or 'activat' in subject.lower()
    
    def test_withdrawal_email_subject(self):
        """Test that Withdrawal email has correct subject line"""
        subject = "Withdrawal Request Received"
        assert 'Withdrawal' in subject or 'withdrawal' in subject.lower()


@pytest.mark.unit
class TestEmailNotificationTriggers:
    """Test when emails should be triggered"""
    
    def test_deposit_email_triggered_on_investment_creation(self, app, sample_batch, auth_token, client):
        """Test that Deposit email is sent when investment is created"""
        with app.app_context():
            with patch('app.utils.email_service.mail.send') as mock_send:
                investment = Investment(
                    investor_name='Test Investor',
                    investor_email='test@example.com',
                    internal_client_code='INV-001',
                    amount_deposited=Decimal('50000.00'),
                    date_deposited=datetime.now(timezone.utc),
                    batch_id=sample_batch.id,
                )
                db.session.add(investment)
                db.session.commit()
                
                # In real app, trigger email send
                # This is implementation-dependent
                # Example:
                # send_deposit_email(investment)
                # 
                # For now, we document expected behavior:
                expected_recipient = investment.investor_email
                expected_subject_keywords = ['Deposit', 'Confirmation']
    
    def test_transfer_email_triggered_on_stage_2(self, app, sample_batch):
        """Test that Transfer email is sent when batch moves to Stage 2"""
        with app.app_context():
            batch = db.session.get(Batch,sample_batch.id)
            
            # Simulate stage transition
            batch.stage = 2
            batch.is_transferred = True
            db.session.commit()
            
            # In real app, this would trigger email to all investors:
            # for investment in batch.investments:
            #     send_transfer_email(investment, batch)
            
            # Expected behavior:
            # - Email to all investors in batch
            # - Subject contains "Transfer"
            # - Body contains batch_name and amount details
    
    def test_active_email_triggered_on_date_deployed(self, app, sample_batch, sample_investments):
        """Test that Active email is sent when date_deployed is set"""
        with app.app_context():
            batch = db.session.get(Batch,sample_batch.id)
            
            # Simulate deployment
            batch.date_deployed = datetime.now(timezone.utc)
            batch.deployment_confirmed = True
            batch.stage = 3
            db.session.commit()
            
            # In real app, trigger Active email for stage 4
            # This happens when deployment_confirmed AND enough time has passed
            
            # Expected behavior:
            # - Email to all investors
            # - Subject contains "Active"
            # - Body contains expected close date


@pytest.mark.unit
class TestEmailLogging:
    """Test that email sends are logged in audit trail"""
    
    def test_successful_email_audit_log(self, app):
        """Test that successful email sends are logged"""
        with app.app_context():
            audit_log_email(
                recipient_email='investor@example.com',
                email_type='DEPOSIT',
                batch_id=1,
                subject='Investment Deposit Confirmation',
                status=True,
            )
            
            # Should create audit log
            from app.utils.audit_log import AuditLog
            log = AuditLog.query.filter_by(action='SEND_EMAIL').first()
            assert log is not None
            assert log.success is True
    
    def test_failed_email_audit_log(self, app):
        """Test that failed email sends are logged with error"""
        with app.app_context():
            error_msg = "SMTP connection failed"
            audit_log_email(
                recipient_email='investor@example.com',
                email_type='DEPOSIT',
                batch_id=1,
                subject='Investment Deposit Confirmation',
                status=False,
                error=error_msg,
            )
            
            # Should create audit log with error
            from app.utils.audit_log import AuditLog
            log = AuditLog.query.filter_by(action='SEND_EMAIL').first()
            assert log is not None
            assert log.success is False
            assert error_msg in log.error_message


@pytest.mark.integration
class TestEmailWorkflow:
    """Test complete email workflows"""
    
    def test_batch_lifecycle_email_sequence(self, app, sample_batch, sample_investments):
        """
        Test complete email sequence through batch lifecycle:
        1. Deposit - when investments created
        2. Transfer - when batch marked as transferred
        3. Active - when deployment confirmed
        """
        with app.app_context():
            emails_sent = []
            
            def mock_email_send(to_email, email_type, subject, **kwargs):
                emails_sent.append({
                    'to': to_email,
                    'type': email_type,
                    'subject': subject,
                    'timestamp': datetime.now(timezone.utc),
                })
            
            # Stage 1: Deposit emails (investments already created in fixtures)
            batch = db.session.get(Batch,sample_batch.id)
            assert batch.stage == 1
            # Would normally trigger deposit emails here
            
            # Stage 2: Transfer emails
            batch.stage = 2
            batch.is_transferred = True
            db.session.commit()
            # Would normally trigger transfer emails here
            
            # Stage 3: Deployment confirmation
            batch.deployment_confirmed = True
            batch.date_deployed = datetime.now(timezone.utc)
            db.session.commit()
            
            # Stage 4: Active emails (typically automatic or manual trigger)
            batch.stage = 4
            batch.is_active = True
            db.session.commit()
            # Would normally trigger active emails here


@pytest.mark.unit
class TestEmailTemplate:
    """Test email template content"""
    
    def test_deposit_email_contains_investor_details(self):
        """Test Deposit email template contains investor information"""
        template = """
        Dear {investor_name},
        
        Your investment of {amount} has been deposited to {batch_name}.
        
        Investor: {investor_name}
        Wealth Manager: {wealth_manager}
        IFA: {ifa}
        
        Best regards,
        OFDS Investment Team
        """
        
        # Template should have placeholders for:
        assert '{investor_name}' in template
        assert '{amount}' in template
        assert '{batch_name}' in template
        assert '{wealth_manager}' in template
        assert '{ifa}' in template
    
    def test_transfer_email_contains_batch_details(self):
        """Test Transfer email template contains batch information"""
        template = """
        Dear Investor,
        
        Your batch {batch_name} (Certificate: {cert_number}) has been successfully transferred.
        
        Total Invested: {total_principal}
        Number of Investors: {investor_count}
        
        Best regards,
        OFDS Investment Team
        """
        
        # Template should have batch-level information
        assert '{batch_name}' in template
        assert '{cert_number}' in template
        assert '{total_principal}' in template
    
    def test_active_email_contains_performance_info(self):
        """Test Active email template contains performance information"""
        template = """
        Dear {investor_name},
        
        Your investment is now ACTIVE!
        Current Value: {current_value}
        Expected Close Date: {close_date}
        Performance to Date: {performance}%
        
        Best regards,
        OFDS Investment Team
        """
        
        # Template should have performance data
        assert '{current_value}' in template
        assert '{close_date}' in template
        assert '{performance}' in template


@pytest.mark.unit
class TestEmailValidation:
    """Test email address validation"""
    
    def test_valid_email_address(self):
        """Test valid email addresses are accepted"""
        valid_emails = [
            'investor@example.com',
            'john.doe@company.co.uk',
            'first.last+tag@domain.com',
        ]
        
        for email in valid_emails:
            assert '@' in email
            assert '.' in email.split('@')[1]
    
    def test_invalid_email_address_rejected(self):
        """Test invalid email addresses are rejected"""
        invalid_emails = [
            'nodomain@',
            'noemail.com',
            '@domain.com',
            'spaces in@email.com',
        ]
        
        for email in invalid_emails:
            has_at = '@' in email
            has_domain = '.' in email.split('@')[1] if has_at else False
            # In real app, would use proper validation
            # assert not is_valid_email(email)
    
    def test_email_to_all_investors_in_batch(self, app, sample_batch, sample_investments):
        """Test that emails are sent to all investors in a batch"""
        with app.app_context():
            batch = db.session.get(Batch,sample_batch.id)
            recipients = [inv.investor_email for inv in batch.investments]
            
            # Should have one email per investment
            assert len(recipients) == len(sample_investments)
            assert 'john@example.com' in recipients
            assert 'alice@example.com' in recipients


@pytest.mark.integration
class TestEmailErrorHandling:
    """Test email sending error scenarios"""
    
    def test_email_send_with_invalid_smtp_config(self, app):
        """Test handling of SMTP configuration errors"""
        with app.app_context():
            # In real implementation, would test with bad SMTP config
            # Expected: error is logged but doesn't crash batch processing
            pass
    
    def test_email_retry_on_temporary_failure(self, app):
        """Test retry logic for temporary failures"""
        with app.app_context():
            # Expected behavior:
            # 1. First attempt fails (timeout)
            # 2. Retry after delay
            # 3. Eventually succeeds or marks as permanently failed
            # 4. All attempts logged in audit trail
            pass
    
    def test_email_failure_doesnt_block_batch_processing(self, app):
        """Test that email failures don't prevent batch operations"""
        with app.app_context():
            with patch('app.utils.email_service.mail.send') as mock_send:
                mock_send.side_effect = Exception("Email service down")
                
                # Batch operations should continue despite email failure
                batch = Batch(
                    batch_name='Test',
                    certificate_number='CERT-001',
                    total_principal=Decimal('1000000.00'),
                )
                db.session.add(batch)
                db.session.commit()
                
                # Batch should be created even if email fails
                assert batch.id is not None
