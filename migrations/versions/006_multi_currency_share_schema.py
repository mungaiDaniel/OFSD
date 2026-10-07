"""Add multi-currency share schema fields

Revision ID: 006_multi_currency_share_schema
Revises: 005_nav_share_based_valuation
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "006_multi_currency_share_schema"
down_revision = "005_nav_share_based_valuation"
branch_labels = None
depends_on = None


def upgrade():
    currency_enum = sa.Enum("USD", "KES", name="currency_type_enum")
    currency_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("investments", sa.Column("original_deposit_amount", sa.Numeric(20, 2), nullable=True))
    op.add_column("investments", sa.Column("current_market_value", sa.Numeric(20, 2), nullable=True))
    op.add_column("investments", sa.Column("currency_type", currency_enum, nullable=True))

    op.alter_column(
        "investments",
        "shares_owned",
        existing_type=sa.Numeric(24, 8),
        type_=sa.Numeric(24, 4),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "investments",
        "shares_owned",
        existing_type=sa.Numeric(24, 4),
        type_=sa.Numeric(24, 8),
        existing_nullable=True,
    )

    op.drop_column("investments", "currency_type")
    op.drop_column("investments", "current_market_value")
    op.drop_column("investments", "original_deposit_amount")

    currency_enum = sa.Enum("USD", "KES", name="currency_type_enum")
    currency_enum.drop(op.get_bind(), checkfirst=True)
