"""Add pending_emails.withdrawal_id (attach the withdrawal statement to withdrawal notices)

Revision ID: 026_pending_email_withdrawal_id
Revises: 025_unit_redemptions
Create Date: 2026-11-16

Nullable, no backfill. WITHDRAWAL_RECEIVED / WITHDRAWAL_APPROVED emails record
which withdrawal they're about so _send_pending_email_now can attach that
withdrawal's statement PDF. The app's startup schema sync (main.py) also adds
it, so running this via `flask db upgrade` is optional — same as 020-025.
"""

from alembic import op

revision = "026_pending_email_withdrawal_id"
down_revision = "025_unit_redemptions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS withdrawal_id INTEGER REFERENCES withdrawals(id) ON DELETE SET NULL")


def downgrade():
    op.execute("ALTER TABLE pending_emails DROP COLUMN IF EXISTS withdrawal_id")
