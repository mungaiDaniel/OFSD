"""Add NAV/share-based valuation schema

Revision ID: 005_nav_share_based_valuation
Revises: 004_create_portfolio_display_cache
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "005_nav_share_based_valuation"
down_revision = "004_create_portfolio_display_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("investments", sa.Column("shares_owned", sa.Numeric(24, 8), nullable=True))
    op.add_column("investments", sa.Column("share_series", sa.String(length=100), nullable=True))

    op.add_column("investment_batch_valuations", sa.Column("nav_at_period_end", sa.Numeric(24, 8), nullable=True))
    op.add_column("investment_batch_valuations", sa.Column("total_shares_at_time", sa.Numeric(24, 8), nullable=True))

    op.create_table(
        "daily_nav",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nav_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("share_series", sa.String(length=100), nullable=False),
        sa.Column("nav_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nav_date", "share_series", name="_daily_nav_date_series_uc"),
    )
    op.create_index("ix_daily_nav_series_date", "daily_nav", ["share_series", "nav_date"], unique=False)


def downgrade():
    op.drop_index("ix_daily_nav_series_date", table_name="daily_nav")
    op.drop_table("daily_nav")

    op.drop_column("investment_batch_valuations", "total_shares_at_time")
    op.drop_column("investment_batch_valuations", "nav_at_period_end")

    op.drop_column("investments", "share_series")
    op.drop_column("investments", "shares_owned")
