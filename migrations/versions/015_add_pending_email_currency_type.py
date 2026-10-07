"""Add currency_type column to pending_emails table

Revision ID: 015_add_pending_email_currency_type
Revises: 014_add_share_class_current_nav
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "015_add_pending_email_currency_type"
down_revision = "014_add_share_class_current_nav"
branch_labels = None
depends_on = None


def upgrade():
    """Adds currency_type to pending_emails."""
    op.add_column(
        "pending_emails",
        sa.Column("currency_type", sa.String(10), nullable=True, server_default="USD"),
    )
    op.create_index(
        "ix_pending_emails_currency_type",
        "pending_emails",
        ["currency_type"],
        unique=False,
    )


def downgrade():
    """Removes currency_type from pending_emails."""
    op.drop_index("ix_pending_emails_currency_type", table_name="pending_emails")
    op.drop_column("pending_emails", "currency_type")
