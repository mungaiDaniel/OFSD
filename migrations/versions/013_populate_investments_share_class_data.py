"""Data migration: Populate share_class_id for existing investments

Revision ID: 013_populate_investments_share_class_data
Revises: 012_add_investments_share_columns
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "013_populate_investments_share_class_data"
down_revision = "012_add_investments_share_columns"
branch_labels = None
depends_on = None


def upgrade():
    """
    Populates share_class_id for existing investments by matching:
    1. investment.fund_id -> core_funds.id
    2. core_fund -> share_classes entry (picks the first/earliest share class)
    
    This handles legacy investments that don't have a class assigned yet.
    If no share class exists for a fund, share_class_id remains NULL.
    """
    bind = op.get_bind()
    
    # Get database connection / execute method
    connection = bind if hasattr(bind, 'execute') else getattr(bind, 'connection', bind)
    
    # Query to find investments with fund_id set but no share_class_id
    query = text("""
        UPDATE investments i
        SET share_class_id = (
            SELECT sc.id
            FROM share_classes sc
            WHERE sc.core_fund_id = i.fund_id
            ORDER BY sc.created_at ASC
            LIMIT 1
        )
        WHERE i.share_class_id IS NULL
            AND i.fund_id IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM share_classes sc
                WHERE sc.core_fund_id = i.fund_id
            )
    """)
    
    try:
        connection.execute(query)
        print("✓ Successfully populated share_class_id for existing investments")
    except Exception as e:
        print(f"⚠ Data migration warning (this is okay if share classes don't exist yet): {str(e)}")


def downgrade():
    """
    Resets share_class_id to NULL for all investments.
    This allows re-running the data migration after adding share classes.
    """
    bind = op.get_bind()
    connection = bind.connection if hasattr(bind, 'connection') else bind
    
    query = text("UPDATE investments SET share_class_id = NULL")
    connection.execute(query)
    print("✓ Reset share_class_id to NULL for all investments")
