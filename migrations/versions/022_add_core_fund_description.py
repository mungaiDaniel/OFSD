"""Add core_funds.description (Task 12 — edit fund/share details)

Revision ID: 022_add_core_fund_description
Revises: 021_add_ngn_currency_type
Create Date: 2026-10-08

Optional free-text description shown and edited on the Funds/Shares detail
page. Nullable, no backfill. The app's startup schema sync (main.py) also
adds it with ADD COLUMN IF NOT EXISTS, so running this is optional.

Also re-asserts that 'NGN' exists in currency_type_enum (same as 021), so a
database that skipped 021 still ends up correct.
"""

from alembic import op

revision = "022_add_core_fund_description"
down_revision = "021_add_ngn_currency_type"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE currency_type_enum ADD VALUE IF NOT EXISTS 'NGN'")
    op.execute("ALTER TABLE core_funds ADD COLUMN IF NOT EXISTS description TEXT")


def downgrade():
    op.execute("ALTER TABLE core_funds DROP COLUMN IF EXISTS description")
