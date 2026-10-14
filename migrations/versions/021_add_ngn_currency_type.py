"""Allow NGN in investments.currency_type (currency_type_enum)

Revision ID: 021_add_ngn_currency_type
Revises: 020_add_fund_product_type
Create Date: 2026-10-08

Migration 020 made DPRP (SHARES) share classes NGN-valued, so investments
created under them now carry currency_type = 'NGN'. The Postgres enum
currency_type_enum only had 'USD' and 'KES', so every such INSERT failed with
"invalid input value for enum currency_type_enum: NGN".
"""

from alembic import op

revision = "021_add_ngn_currency_type"
down_revision = "020_add_fund_product_type"
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE ... ADD VALUE must be committed before the value can be used
    # (and cannot run in a transaction block on Postgres < 12).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE currency_type_enum ADD VALUE IF NOT EXISTS 'NGN'")


def downgrade():
    # Postgres cannot drop a single enum value. Rows using NGN would have to be
    # converted and the type rebuilt by hand, so this is intentionally a no-op.
    pass
