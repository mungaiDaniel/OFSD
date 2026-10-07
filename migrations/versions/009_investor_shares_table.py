"""Create investor_shares table to track investor share holdings

Revision ID: 009_investor_shares_table
Revises: 008_nav_history_table
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "009_investor_shares_table"
down_revision = "008_nav_history_table"
branch_labels = None
depends_on = None


def upgrade():
    """
    Creates the investor_shares table to track individual investor share holdings.
    
    Each row represents:
    - An investor's holdings in a specific share class
    - Within a specific batch context
    - With the deployment NAV they entered at (for cost basis tracking)
    """
    op.create_table(
        "investor_shares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("investment_id", sa.Integer(), nullable=False),
        sa.Column("share_class_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("shares_owned", sa.Numeric(20, 6), nullable=False),
        sa.Column("deployment_nav", sa.Numeric(20, 6), nullable=False),
        sa.Column("deployment_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["investment_id"],
            ["investments.id"],
            name="_investor_shares_investment_fk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["share_class_id"],
            ["share_classes.id"],
            name="_investor_shares_share_class_fk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            name="_investor_shares_batch_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investor_shares_investment_id",
        "investor_shares",
        ["investment_id"],
        unique=False,
    )
    op.create_index(
        "ix_investor_shares_share_class_id",
        "investor_shares",
        ["share_class_id"],
        unique=False,
    )
    op.create_index(
        "ix_investor_shares_batch_id",
        "investor_shares",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_investor_shares_active",
        "investor_shares",
        ["is_active"],
        unique=False,
    )


def downgrade():
    """
    Drops the investor_shares table and all associated indices.
    """
    op.drop_index("ix_investor_shares_active", table_name="investor_shares")
    op.drop_index("ix_investor_shares_batch_id", table_name="investor_shares")
    op.drop_index("ix_investor_shares_share_class_id", table_name="investor_shares")
    op.drop_index("ix_investor_shares_investment_id", table_name="investor_shares")
    op.drop_table("investor_shares")
