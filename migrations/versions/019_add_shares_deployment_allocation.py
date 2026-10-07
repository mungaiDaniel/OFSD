"""Add SHARES deployment allocation fields (USD->NGN conversion)

Revision ID: 019_add_shares_deployment_allocation
Revises: 018_add_shares_balance_after_entry_fee
Create Date: 2026-10-07

Task 3: SHARES (DPRP) batches at the Deployed transition convert net_usd per
deposit to NGN and allocate whole shares (see
app.logic.shares_deployment_service). Replaces the old flat-rate DPRP
oversubscription allocation (is_oversubscribed/allocation_rate on Batch
remain as columns — now unused by new code, kept only for historical
batches deployed under the old system).

Run with: flask db upgrade
Rollback with: flask db downgrade
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "019_add_shares_deployment_allocation"
down_revision = "018_add_shares_balance_after_entry_fee"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_exchange_rate_ngn NUMERIC(20, 6)"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_price_per_share_ngn NUMERIC(20, 4)"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_allocated_total INTEGER"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_demand_total INTEGER"))
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_unallocated_total INTEGER"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_exchange_rate_ngn NUMERIC(20, 6)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_price_per_share_ngn NUMERIC(20, 4)"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS net_ngn NUMERIC(20, 2)"))


def downgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE investments DROP COLUMN IF EXISTS net_ngn"))
    conn.execute(text("ALTER TABLE investments DROP COLUMN IF EXISTS shares_price_per_share_ngn"))
    conn.execute(text("ALTER TABLE investments DROP COLUMN IF EXISTS shares_exchange_rate_ngn"))
    conn.execute(text("ALTER TABLE batches DROP COLUMN IF EXISTS shares_unallocated_total"))
    conn.execute(text("ALTER TABLE batches DROP COLUMN IF EXISTS shares_demand_total"))
    conn.execute(text("ALTER TABLE batches DROP COLUMN IF EXISTS shares_allocated_total"))
    conn.execute(text("ALTER TABLE batches DROP COLUMN IF EXISTS shares_price_per_share_ngn"))
    conn.execute(text("ALTER TABLE batches DROP COLUMN IF EXISTS shares_exchange_rate_ngn"))
