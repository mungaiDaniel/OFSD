"""Add current_nav column to share_classes

Revision ID: 014_add_share_class_current_nav
Revises: 013_populate_investments_share_class_data
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa

revision = "014_add_share_class_current_nav"
down_revision = "013_populate_investments_share_class_data"
branch_labels = None
depends_on = None


def upgrade():
    """Adds current_nav to share_classes."""
    op.add_column(
        "share_classes",
        sa.Column("current_nav", sa.Numeric(20, 6), nullable=True),
    )
    op.create_index(
        "ix_share_classes_current_nav",
        "share_classes",
        ["current_nav"],
        unique=False,
    )


def downgrade():
    """Removes current_nav from share_classes."""
    op.drop_index("ix_share_classes_current_nav", table_name="share_classes")
    op.drop_column("share_classes", "current_nav")
