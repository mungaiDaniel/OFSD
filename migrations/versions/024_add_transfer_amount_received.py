"""Add investments.transfer_amount_received (manual per-investor Transfer amounts, FUNDS)

Revision ID: 024_add_transfer_amount_received
Revises: 023_shares_deposit_currency_usd
Create Date: 2026-10-14

Nullable, no backfill. Lets an admin type in the real amount that landed in
the bank for each investor at the FUNDS "Advance to Transfer" step, instead
of (or alongside) the legacy pro-rata transaction-cost formula — see
StatusUpdateController._apply_transfer_cost_deduction. NULL on any
investment whose batch used the legacy pro-rata formula.

The app's startup schema sync (main.py) also adds it with
ADD COLUMN IF NOT EXISTS, so running this via `flask db upgrade` is optional
(and, per README/earlier migrations, the full migration chain isn't safely
runnable today — see 003_dedup_investor_batch_records.py). This file exists
for documentation/history, matching the pattern of 020-022.
"""

from alembic import op

revision = "024_add_transfer_amount_received"
down_revision = "023_shares_deposit_currency_usd"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE investments ADD COLUMN IF NOT EXISTS transfer_amount_received NUMERIC(20, 2)")


def downgrade():
    op.execute("ALTER TABLE investments DROP COLUMN IF EXISTS transfer_amount_received")
