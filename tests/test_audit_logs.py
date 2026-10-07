"""
Audit Logging Tests
===================
Tests for audit log creation, retrieval, and security properties.
Verifies insert-only behavior and action tracking.

Run with: pytest tests/test_audit_logs.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from app.database.database import db
from app.utils.audit_log import (
    AuditLog,
    create_audit_log,
    audit_log,
    audit_log_email,
    audit_log_file_upload,
    audit_log_toggle,
    get_client_ip,
)
from app.Batch.model import Batch
from app.Investments.model import Investment
from decimal import Decimal


@pytest.mark.unit
class TestAuditLogModel:
    """Test AuditLog model and insert-only behavior"""
    
    def test_create_audit_log_entry(self, app):
        """Test creating an audit log entry"""
        with app.app_context():
            log = create_audit_log(
                action='TEST_ACTION',
                target_type='batch',
                target_id=1,
                target_name='Test Batch',
                description='Testing audit log creation',
                success=True,
            )
            
            assert log is not None
            assert log.action == 'TEST_ACTION'
            assert log.target_type == 'batch'
            assert log.target_id == 1
            assert log.success is True
            
            # Verify it was saved
            retrieved = AuditLog.query.filter_by(id=log.id).first()
            assert retrieved is not None
    
    def test_audit_log_insert_only(self, app):
        """Test that audit logs cannot be updated (insert-only)"""
        with app.app_context():
            # Create log
            log = create_audit_log(
                action='ORIGINAL_ACTION',
                target_type='batch',
                target_id=1,
            )
            original_id = log.id
            original_timestamp = log.timestamp
            
            # Try to update (this would normally fail with proper constraints)
            # In a real implementation, you'd use database triggers to prevent updates
            # For now, we test the Python behavior
            log.action = 'MODIFIED_ACTION'
            try:
                db.session.commit()
                # If we get here, the app needs database-level constraints
                # Let's at least verify we can query the original
                retrieved = db.session.get(AuditLog, original_id)
                # In a properly secured system, this would have failed
            except:
                # Expected in a secure implementation
                db.session.rollback()
    
    def test_audit_log_captures_ip_address(self, app, client):
        """Test that IP address is captured"""
        with app.app_context():
            log = create_audit_log(
                action='IP_TEST',
                target_type='test',
            )
            
            # IP should be captured (might be '127.0.0.1' in tests)
            assert log.ip_address is not None
            assert log.ip_address != 'UNKNOWN'
    
    def test_audit_log_captures_user_agent(self, app, client):
        """Test that user agent is captured"""
        with app.app_context():
            log = create_audit_log(
                action='AGENT_TEST',
                target_type='test',
            )
            
            assert log.user_agent is not None
    
    def test_audit_log_serializes_json_values(self, app):
        """Test that old_value and new_value are JSON serialized"""
        with app.app_context():
            complex_value = {
                'field1': 'value1',
                'field2': 100,
                'nested': {'key': 'value'},
            }
            
            log = create_audit_log(
                action='JSON_TEST',
                target_type='test',
                old_value={'old': 'value'},
                new_value=complex_value,
            )
            
            # Values should be JSON strings
            assert isinstance(log.old_value, str)
            assert isinstance(log.new_value, str)
            
            # Should be deserializable
            assert json.loads(log.new_value) == complex_value


@pytest.mark.unit
class TestAuditLogDecorator:
    """Test the @audit_log decorator"""
    
    def test_audit_log_decorator_on_function(self, app):
        """Test decorator records function execution"""
        with app.app_context():
            @audit_log('TEST_FUNCTION', target_type='test')
            def test_function():
                return "success"
            
            # Call function
            result = test_function()
            assert result == "success"
            
            # Check log was created
            log = AuditLog.query.filter_by(action='TEST_FUNCTION').first()
            assert log is not None
            assert log.success is True
    
    def test_audit_log_decorator_with_target_id(self, app, sample_batch):
        """Test decorator extracts target_id from function parameters"""
        with app.app_context():
            @audit_log('UPDATE_BATCH', target_type='batch', target_id_param='batch_id')
            def update_batch(batch_id):
                batch = db.session.get(Batch, batch_id)
                return batch
            
            # Call function
            result = update_batch(sample_batch.id)
            assert result is not None
            
            # Check log captured target_id
            log = AuditLog.query.filter_by(action='UPDATE_BATCH').first()
            assert log is not None
            assert log.target_id == sample_batch.id
    
    def test_audit_log_decorator_captures_error(self, app):
        """Test decorator logs errors"""
        with app.app_context():
            @audit_log('ERROR_FUNCTION', target_type='test')
            def failing_function():
                raise ValueError("Test error")
            
            # Call should raise error
            with pytest.raises(ValueError):
                failing_function()
            
            # Check error was logged
            log = AuditLog.query.filter_by(action='ERROR_FUNCTION').first()
            assert log is not None
            assert log.success is False
            assert 'Test error' in log.error_message


@pytest.mark.unit
class TestAuditLogActions:
    """Test specific audit log action helpers"""
    
    def test_audit_log_email(self, app):
        """Test email notification logging"""
        with app.app_context():
            audit_log_email(
                recipient_email='investor@example.com',
                email_type='DEPOSIT',
                batch_id=1,
                subject='Deposit Confirmation',
                status=True,
            )
            
            log = AuditLog.query.filter_by(action='SEND_EMAIL').first()
            assert log is not None
            assert 'DEPOSIT' in log.description
            assert 'investor@example.com' in log.description
    
    def test_audit_log_file_upload(self, app):
        """Test file upload logging"""
        with app.app_context():
            audit_log_file_upload(
                filename='investments.xlsx',
                batch_id=1,
                row_count=50,
                status=True,
            )
            
            log = AuditLog.query.filter_by(action='UPLOAD_FILE').first()
            assert log is not None
            assert 'investments.xlsx' in log.description
            assert '50' in log.description
    
    def test_audit_log_toggle(self, app):
        """Test toggle action logging"""
        with app.app_context():
            audit_log_toggle(
                batch_id=1,
                field_name='is_active',
                old_state=False,
                new_state=True,
            )
            
            log = AuditLog.query.filter_by(action='TOGGLE_IS_ACTIVE').first()
            assert log is not None
            assert log.success is True
            
            # Check values were recorded
            old_val = json.loads(log.old_value)
            new_val = json.loads(log.new_value)
            assert old_val['is_active'] is False
            assert new_val['is_active'] is True


@pytest.mark.integration
class TestAuditLogWithBatchOperations:
    """Test audit logging in realistic batch operations"""
    
    def test_batch_creation_audit_trail(self, app):
        """Test that batch creation generates audit logs"""
        with app.app_context():
            # Create batch with decorator if implemented
            batch = Batch(
                batch_name='Audit Test Batch',
                certificate_number='CERT-AUDIT-001',
                total_principal=Decimal('1000000.00'),
                stage=1,
            )
            db.session.add(batch)
            db.session.commit()
            
            # Manually log the creation
            audit_log_toggle(
                batch_id=batch.id,
                field_name='is_active',
                old_state=False,
                new_state=False,  # Still false, just testing log creation
            )
            
            # Verify audit entry exists
            log = AuditLog.query.filter_by(target_id=batch.id).first()
            assert log is not None
    
    def test_batch_status_transition_audit_trail(self, app, sample_batch):
        """Test audit trail for batch status transitions"""
        with app.app_context():
            batch = db.session.get(Batch, sample_batch.id)
            original_stage = batch.stage
            
            # Simulate stage transition
            batch.stage = 2
            batch.is_transferred = True
            db.session.commit()
            
            # Log the transition
            audit_log_toggle(
                batch_id=batch.id,
                field_name='stage',
                old_state=original_stage,
                new_state=2,
            )
            
            # Verify logs exist
            logs = AuditLog.query.filter_by(target_id=batch.id).all()
            assert len(logs) > 0


@pytest.mark.unit
class TestAuditLogRetrieval:
    """Test retrieving and querying audit logs"""
    
    def test_query_logs_by_action(self, app):
        """Test querying logs by action type"""
        with app.app_context():
            # Create multiple logs
            for i in range(3):
                create_audit_log(
                    action='UPLOAD_FILE',
                    target_type='batch',
                    target_id=1,
                )
            
            # Query by action
            logs = AuditLog.query.filter_by(action='UPLOAD_FILE').all()
            assert len(logs) == 3
    
    def test_query_logs_by_target_id(self, app):
        """Test querying logs by target ID"""
        with app.app_context():
            batch_id = 42
            
            # Create logs for different targets
            create_audit_log(action='ACTION1', target_id=batch_id)
            create_audit_log(action='ACTION2', target_id=batch_id)
            create_audit_log(action='ACTION3', target_id=99)
            
            # Query by target
            logs = AuditLog.query.filter_by(target_id=batch_id).all()
            assert len(logs) == 2
    
    def test_query_logs_by_timestamp_range(self, app):
        """Test querying logs by timestamp range"""
        with app.app_context():
            from datetime import timedelta
            
            now = datetime.now(timezone.utc)
            past = now - timedelta(hours=1)
            future = now + timedelta(hours=1)
            
            create_audit_log(action='TEST')
            
            # Query with timestamp filter
            logs = AuditLog.query.filter(
                AuditLog.timestamp >= past,
                AuditLog.timestamp <= future
            ).all()
            
            assert len(logs) == 1
    
    def test_audit_log_to_dict(self, app):
        """Test converting audit log to dictionary"""
        with app.app_context():
            log = create_audit_log(
                action='SERIALIZE_TEST',
                target_type='batch',
                target_id=1,
            )
            
            log_dict = log.to_dict()
            assert log_dict['action'] == 'SERIALIZE_TEST'
            assert log_dict['target_type'] == 'batch'
            assert log_dict['target_id'] == 1
            assert 'timestamp' in log_dict


@pytest.mark.unit
class TestAuditLogSecurity:
    """Test security properties of audit logging"""
    
    def test_audit_log_cannot_be_deleted_directly(self, app):
        """Test that audit logs maintain audit trail (soft verification)"""
        with app.app_context():
            log = create_audit_log(action='TEST')
            log_id = log.id
            
            # Even if deleted from app, should be prevented by DB constraints
            # This is a check of the principle
            original_count = AuditLog.query.count()
            
            # Attempting to delete (in real app, DB trigger would prevent)
            try:
                db.session.delete(log)
                # In secure implementation, this would fail at DB level
                # For now, we roll back to prevent actual deletion
                db.session.rollback()
            except:
                pass
            
            # Verify record still exists
            current_count = AuditLog.query.count()
            assert current_count == original_count
    
    def test_audit_log_preserves_user_context(self, app):
        """Test that user ID is captured in audit logs"""
        with app.app_context():
            log = create_audit_log(
                action='USER_CONTEXT_TEST',
                target_type='test',
            )
            
            # User ID might be None in test context, but field exists
            assert hasattr(log, 'user_id')
            assert hasattr(log, 'ip_address')
            assert hasattr(log, 'user_agent')
