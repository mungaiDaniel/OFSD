"""Add balance_after_entry_fee_usd for SHARES transfer-fee calculation

Revision ID: 018_add_shares_balance_after_entry_fee
Revises: 017_add_product_type
Create Date: 2026-10-07

SHARES (DPRP) batches compute, per deposit at the Transferred stage:
entry_fee_usd -> deployment_fee_deducted, balance_after_entry -> this new
column, transaction_cost_usd -> transfer_fee_deducted (reusing the same two
columns FUNDS already stores its transfer-stage fees in). FUNDS investments
never populate this column.

Run with: flask db upgrade
Rollback with: flask db downgrade
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "018_add_shares_balance_after_entry_fee"
down_revision = "017_add_product_type"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE investments ADD COLUMN IF NOT EXISTS balance_after_entry_fee_usd NUMERIC(20, 2)"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(text(
        "ALTER TABLE investments DROP COLUMN IF EXISTS balance_after_entry_fee_usd"
    ))
