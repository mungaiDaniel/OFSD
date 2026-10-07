"""Add share-based valuation columns to batches table

Revision ID: 011_add_batches_share_columns
Revises: 010_valuation_snapshots_table
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "011_add_batches_share_columns"
down_revision = "010_valuation_snapshots_table"
branch_labels = None
depends_on = None


def upgrade():
    """
    Adds share-based valuation tracking columns to the batches table.
    
    New columns support:
    - share_class_id: Link batch to a specific share class (nullable for legacy batches)
    - is_open: Track whether batch is still accepting new investors
    - auto_close_at: Automatic close timestamp (next Thursday 9:00 AM EAT)
    - exported_at: Track when batch Excel export was generated
    - total_shares: Running total of all shares in batch
    - deployment_nav: NAV at time of deployment
    - deployment_date_actual: Actual deployment date from Head Office confirmation
    """
    op.add_column(
        "batches",
        sa.Column("share_class_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "batches",
        sa.Column("auto_close_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("total_shares", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("deployment_nav", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("deployment_date_actual", sa.Date(), nullable=True),
    )

    # Create foreign key constraint for share_class_id
    op.create_foreign_key(
        "_batches_share_class_fk",
        "batches",
        "share_classes",
        ["share_class_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create index on (share_class_id, is_open) for efficient lookup of open batches per class
    op.create_index(
        "ix_batches_share_class_is_open",
        "batches",
        ["share_class_id", "is_open"],
        unique=False,
    )


def downgrade():
    """
    Removes share-based valuation columns and indices from batches table.
    """
    op.drop_index("ix_batches_share_class_is_open", table_name="batches")

    op.drop_constraint("_batches_share_class_fk", "batches", type_="foreignkey")

    op.drop_column("batches", "deployment_date_actual")
    op.drop_column("batches", "deployment_nav")
    op.drop_column("batches", "total_shares")
    op.drop_column("batches", "exported_at")
    op.drop_column("batches", "auto_close_at")
    op.drop_column("batches", "is_open")
    op.drop_column("batches", "share_class_id")
