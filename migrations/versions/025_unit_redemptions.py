"""Unit-based redemptions: withdrawals.shares_redeemed/redemption_nav/... + withdrawal_lots

Revision ID: 025_unit_redemptions
Revises: 024_add_transfer_amount_received
Create Date: 2026-11-16

A NAV-fund withdrawal can now be recorded the way the transfer agent books
it (e.g. a Janus Henderson contract note): shares redeemed x NAV on the trade
date. Executing it reduces the client's InvestorShares (oldest lot first,
recorded in withdrawal_lots) — see app/logic/redemption_service.py. All new
columns are nullable; existing (cash-only) withdrawals are unchanged.

The app's startup schema sync (main.py) also adds these, so running this via
`flask db upgrade` is optional — same pattern as 020-024.
"""

from alembic import op

revision = "025_unit_redemptions"
down_revision = "024_add_transfer_amount_received"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS shares_redeemed NUMERIC(24, 6)")
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS redemption_nav NUMERIC(20, 6)")
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS share_class_id INTEGER REFERENCES share_classes(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS trade_date DATE")
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS settlement_date DATE")
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS ta_reference VARCHAR(50)")
    op.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ")
    op.execute("""
        CREATE TABLE IF NOT EXISTS withdrawal_lots (
            id SERIAL PRIMARY KEY,
            withdrawal_id INTEGER NOT NULL REFERENCES withdrawals(id) ON DELETE CASCADE,
            investor_shares_id INTEGER NOT NULL REFERENCES investor_shares(id) ON DELETE CASCADE,
            investment_id INTEGER NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
            batch_id INTEGER REFERENCES batches(id),
            shares_redeemed NUMERIC(24, 6) NOT NULL,
            shares_before NUMERIC(24, 6) NOT NULL,
            deployment_nav NUMERIC(20, 6),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_withdrawal_lots_withdrawal_id ON withdrawal_lots (withdrawal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_withdrawal_lots_investor_shares_id ON withdrawal_lots (investor_shares_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS withdrawal_lots")
    for col in ("executed_at", "ta_reference", "settlement_date", "trade_date", "share_class_id", "redemption_nav", "shares_redeemed"):
        op.execute(f"ALTER TABLE withdrawals DROP COLUMN IF EXISTS {col}")
