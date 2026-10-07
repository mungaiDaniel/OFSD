"""Complete production schema sync and activate existing users

Revision ID: 016_complete_production_schema_sync
Revises: 015_add_pending_email_currency_type
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "016_complete_production_schema_sync"
down_revision = "015_add_pending_email_currency_type"
branch_labels = None
depends_on = None


def upgrade():
    """
    Ensures all tables, columns, indexes, and user status/roles are fully synchronized
    and idempotent. Existing users are ensured to be 'active'.
    """
    conn = op.get_bind()

    # 1. Enums
    conn.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'currency_type_enum') THEN
                CREATE TYPE currency_type_enum AS ENUM ('USD', 'KES');
            END IF;
        END $$;
    """))

    # 2. User table columns & activate existing users
    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'"))
    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'"))
    
    # Ensure all existing users are activated and have valid roles
    conn.execute(text("UPDATE \"user\" SET status = 'active' WHERE status IS NULL OR status = 'pending'"))
    conn.execute(text("""
        UPDATE "user"
        SET role = CASE
            WHEN role IS NULL OR role = '' THEN 'admin'
            WHEN role = 'superadmin' THEN 'super_admin'
            ELSE role
        END
    """))

    # 3. Share classes columns
    conn.execute(text("ALTER TABLE share_classes ADD COLUMN IF NOT EXISTS current_nav NUMERIC(20, 6)"))

    # 4. Batches table columns (complete guarantee)
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS share_class_id INTEGER"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS is_open BOOLEAN DEFAULT TRUE"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_close_at TIMESTAMPTZ"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS exported_at TIMESTAMPTZ"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS total_shares NUMERIC(20, 6)"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS deployment_nav NUMERIC(20, 6)"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS deployment_date_actual DATE"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS transfer_transaction_cost NUMERIC(20, 2) DEFAULT 0.00"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS cached_total_capital NUMERIC(20, 2)"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS cached_total_capital_at TIMESTAMPTZ"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS deployment_total_nav NUMERIC(20, 2)"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS deployment_breakdown TEXT"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS is_oversubscribed BOOLEAN DEFAULT FALSE"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS allocation_rate NUMERIC(7, 4)"))

    # 5. Investments table columns (complete guarantee)
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS share_class_id INTEGER"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS deposit_date DATE"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS transfer_fee_deducted NUMERIC(20, 2) DEFAULT 0.00"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS share_series VARCHAR(100)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_owned NUMERIC(24, 4)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS original_deposit_amount NUMERIC(20, 2)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS current_market_value NUMERIC(20, 2)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS opening_market_value NUMERIC(20, 2)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS previous_nav_price NUMERIC(20, 6)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS rounding_adjustment NUMERIC(20, 4) DEFAULT 0.0000"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS official_receipt_value NUMERIC(20, 2)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS currency_type currency_type_enum"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS oversubscription_refund_amount NUMERIC(20, 2) DEFAULT 0.00"))

    # 6. Withdrawals table columns
    conn.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'investor_request'"))
    conn.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS oversubscription_notice_sent_at TIMESTAMPTZ"))

    # 7. Pending emails & Email logs
    conn.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS currency_type VARCHAR(10) DEFAULT 'USD'"))
    conn.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
    conn.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS queued_at TIMESTAMPTZ"))
    conn.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS statement_fund_ids VARCHAR(255)"))
    conn.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))

    # 8. Audit logs
    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_email VARCHAR(120)"))
    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_name VARCHAR(120)"))

    # 9. Indexes (all IF NOT EXISTS)
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pending_emails_currency_type ON pending_emails (currency_type)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pending_emails_queued_at ON pending_emails (queued_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_batches_share_class_is_open ON batches (share_class_id, is_open)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_share_class_id ON investments (share_class_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_internal_client_code ON investments (internal_client_code)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_lower_client_code ON investments (lower(internal_client_code))"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_batch_id ON investments (batch_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_fund_id ON investments (fund_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_date_deposited ON investments (date_deposited)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_withdrawals_source ON withdrawals (source)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_withdrawals_lower_client_code ON withdrawals (lower(internal_client_code))"))

    # 10. Additional application tables
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS upload_column_mappings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            template_key VARCHAR(64) NOT NULL,
            source_headers TEXT NOT NULL,
            mapping_json TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT _upload_mapping_user_template_uc UNIQUE (user_id, template_key)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS bulk_upload_jobs (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255),
            status VARCHAR(20) DEFAULT 'queued' NOT NULL,
            total_rows INTEGER DEFAULT 0 NOT NULL,
            processed_rows INTEGER DEFAULT 0 NOT NULL,
            succeeded_count INTEGER DEFAULT 0 NOT NULL,
            failed_count INTEGER DEFAULT 0 NOT NULL,
            error_message TEXT,
            rows_payload TEXT,
            errors_payload TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            completed_at TIMESTAMPTZ
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS email_settings (
            id SERIAL PRIMARY KEY,
            mail_server VARCHAR(255),
            mail_port INTEGER,
            mail_use_tls BOOLEAN,
            mail_use_ssl BOOLEAN,
            mail_username VARCHAR(255),
            mail_password_encrypted TEXT,
            mail_default_sender VARCHAR(255),
            mail_bcc VARCHAR(255),
            email_queue_batch_size INTEGER,
            email_queue_interval_minutes INTEGER,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_by VARCHAR(120)
        )
    """))


def downgrade():
    """No-op downgrade for safety in production."""
    pass
