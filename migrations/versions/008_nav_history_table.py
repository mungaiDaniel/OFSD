"""Create nav_history table for NAV price tracking per share class

Revision ID: 008_nav_history_table
Revises: 007_share_classes_table
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "008_nav_history_table"
down_revision = "007_share_classes_table"
branch_labels = None
depends_on = None


def upgrade():
    """
    Creates the nav_history table to store historical NAV prices per share class.
    
    The (share_class_id, nav_date, source) composite unique constraint ensures:
    - Only ONE NAV per share class per date per source type
    - Prevents duplicate NAV entries for the same date/source combination
    """
    op.create_table(
        "nav_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("share_class_id", sa.Integer(), nullable=False),
        sa.Column("nav_date", sa.Date(), nullable=False),
        sa.Column("nav_per_share", sa.Numeric(20, 6), nullable=False),
        sa.Column("total_fund_nav", sa.Numeric(20, 2), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            sa.CheckConstraint(
                "source IN ('deployment', 'valuation')",
                name="_nav_source_check",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["share_class_id"],
            ["share_classes.id"],
            name="_nav_history_share_class_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "share_class_id",
            "nav_date",
            "source",
            name="_nav_history_class_date_source_uc",
        ),
    )
    op.create_index(
        "ix_nav_history_share_class_date",
        "nav_history",
        ["share_class_id", "nav_date"],
        unique=False,
    )
    op.create_index(
        "ix_nav_history_date", "nav_history", ["nav_date"], unique=False
    )
    op.create_index(
        "ix_nav_history_source", "nav_history", ["source"], unique=False
    )


def downgrade():
    """
    Drops the nav_history table and all associated indices.
    """
    op.drop_index("ix_nav_history_source", table_name="nav_history")
    op.drop_index("ix_nav_history_date", table_name="nav_history")
    op.drop_index("ix_nav_history_share_class_date", table_name="nav_history")
    op.drop_table("nav_history")
