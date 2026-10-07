"""Add share_class_id and deposit_date to investments table

Revision ID: 012_add_investments_share_columns
Revises: 011_add_batches_share_columns
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "012_add_investments_share_columns"
down_revision = "011_add_batches_share_columns"
branch_labels = None
depends_on = None


def upgrade():
    """
    Adds share-based valuation columns to the investments table.
    
    New columns support:
    - share_class_id: Link investment to a specific share class (nullable for legacy investments)
    - deposit_date: Actual date client deposited money (distinct from system timestamp date_deposited)
    """
    op.add_column(
        "investments",
        sa.Column("share_class_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "investments",
        sa.Column("deposit_date", sa.Date(), nullable=True),
    )

    # Create foreign key constraint for share_class_id
    op.create_foreign_key(
        "_investments_share_class_fk",
        "investments",
        "share_classes",
        ["share_class_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create index on share_class_id for efficient queries
    op.create_index(
        "ix_investments_share_class_id",
        "investments",
        ["share_class_id"],
        unique=False,
    )


def downgrade():
    """
    Removes share-based valuation columns and indices from investments table.
    """
    op.drop_index("ix_investments_share_class_id", table_name="investments")

    op.drop_constraint("_investments_share_class_fk", "investments", type_="foreignkey")

    op.drop_column("investments", "deposit_date")
    op.drop_column("investments", "share_class_id")
