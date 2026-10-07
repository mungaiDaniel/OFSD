"""Create valuation_snapshots table for point-in-time valuation records

Revision ID: 010_valuation_snapshots_table
Revises: 009_investor_shares_table
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "010_valuation_snapshots_table"
down_revision = "009_investor_shares_table"
branch_labels = None
depends_on = None


def upgrade():
    """
    Creates the valuation_snapshots table to store point-in-time valuations.
    
    Each row is a "frozen" snapshot of an investor's holding valuation on a specific date:
    - Captures the NAV, share count, market value, and performance at that moment
    - Enables historical reporting and reconciliation
    - Supports the "Historical Statement is Golden Source" principle
    
    The (investor_shares_id, valuation_date) unique constraint ensures:
    - Only ONE valuation per holding per date
    - Prevents duplicate snapshots for the same holding/date combination
    """
    op.create_table(
        "valuation_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("investor_shares_id", sa.Integer(), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("nav_per_share", sa.Numeric(20, 6), nullable=False),
        sa.Column("shares_held", sa.Numeric(20, 6), nullable=False),
        sa.Column("market_value", sa.Numeric(20, 2), nullable=False),
        sa.Column("performance_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["investor_shares_id"],
            ["investor_shares.id"],
            name="_valuation_snapshots_investor_shares_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "investor_shares_id",
            "valuation_date",
            name="_valuation_snapshots_shares_date_uc",
        ),
    )
    op.create_index(
        "ix_valuation_snapshots_valuation_date",
        "valuation_snapshots",
        ["valuation_date"],
        unique=False,
    )
    op.create_index(
        "ix_valuation_snapshots_investor_shares_id",
        "valuation_snapshots",
        ["investor_shares_id"],
        unique=False,
    )


def downgrade():
    """
    Drops the valuation_snapshots table and all associated indices.
    """
    op.drop_index("ix_valuation_snapshots_investor_shares_id", table_name="valuation_snapshots")
    op.drop_index("ix_valuation_snapshots_valuation_date", table_name="valuation_snapshots")
    op.drop_table("valuation_snapshots")
