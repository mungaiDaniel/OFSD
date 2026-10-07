"""Create share_classes table for fund share series management

Revision ID: 007_share_classes_table
Revises: 006_multi_currency_share_schema
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "007_share_classes_table"
down_revision = "006_multi_currency_share_schema"
branch_labels = None
depends_on = None


def upgrade():
    """
    Creates the share_classes table with:
    - Composite unique constraint on (core_fund_id, class_code)
    - CHECK constraint ensuring each class has exactly ONE currency
    """
    op.create_table(
        "share_classes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("core_fund_id", sa.Integer(), nullable=False),
        sa.Column("class_name", sa.String(length=100), nullable=False),
        sa.Column("class_code", sa.String(length=20), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            sa.CheckConstraint("currency IN ('KES', 'USD')", name="_currency_check"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["core_fund_id"],
            ["core_funds.id"],
            name="_share_classes_core_fund_fk",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_code", name="_share_classes_code_uc"),
        sa.UniqueConstraint(
            "core_fund_id", "class_code", name="_share_classes_fund_code_uc"
        ),
    )
    op.create_index(
        "ix_share_classes_fund_id", "share_classes", ["core_fund_id"], unique=False
    )
    op.create_index(
        "ix_share_classes_active", "share_classes", ["is_active"], unique=False
    )


def downgrade():
    """
    Drops the share_classes table and all associated indices.
    """
    op.drop_index("ix_share_classes_active", table_name="share_classes")
    op.drop_index("ix_share_classes_fund_id", table_name="share_classes")
    op.drop_table("share_classes")
