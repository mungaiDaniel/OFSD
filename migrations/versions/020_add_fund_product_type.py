"""Separate SHARES (DPRP) from FUNDS at the fund level via core_funds.product_type

Revision ID: 020_add_fund_product_type
Revises: 019_add_shares_deployment_allocation
Create Date: 2026-10-07

Task 8: moves the FUNDS/SHARES classification up to where it actually
belongs — core_funds.product_type is now the authoritative source of truth,
instead of batches/investments (migration 017) each independently guessing
it from fund name/code via app.utils.statement_theme.is_dangote_dprp_fund.
share_classes.product_type is added too and backfilled from its parent
core_fund (ShareClass/Batch/Investment each inherit and validate their
product_type against the row above them from here on — see the
before_insert events in app/Funds/share_class.py, app/Batch/model.py, and
the existing one in app/Investments/model.py).

Every existing core_fund identified as DPRP (Dangote Petroleum Refinery and
Petrochemicals — the exact same name/code match used by migration 017 and
is_dangote_dprp_fund) is backfilled to SHARES; everything else becomes
FUNDS. share_classes.currency's CHECK constraint is widened to allow 'NGN'
(SHARES/DPRP is NGN-valued — see Task 7), and DPRP's own share class(es),
which Task 3 had set to 'USD' only because NGN wasn't a legal value yet at
the time, are corrected to 'NGN'. No IDs, amounts, shares, NAV history or
audit records are otherwise touched.

SAFETY: this migration requires explicit confirmation that a database backup
has been taken (set OFSD_CONFIRM_BACKUP=yes in the environment running
`flask db upgrade` / `alembic upgrade`) before it will touch any data.

Run with: flask db upgrade
Rollback with: flask db downgrade
"""

import json
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "020_add_fund_product_type"
down_revision = "019_add_shares_deployment_allocation"
branch_labels = None
depends_on = None


def _require_backup_confirmation():
    if os.environ.get("OFSD_CONFIRM_BACKUP", "").strip().lower() not in ("yes", "true", "1"):
        raise RuntimeError(
            "Refusing to run migration 020_add_fund_product_type without a confirmed backup.\n"
            "This migration backfills product_type on every row of core_funds and share_classes,\n"
            "and corrects DPRP's share class currency from USD to NGN.\n"
            "Take a database backup, then re-run with OFSD_CONFIRM_BACKUP=yes set, e.g.:\n"
            "  pg_dump \"$DATABASE_URL\" -Fc -f pre_020_fund_product_type_backup.dump\n"
            "  OFSD_CONFIRM_BACKUP=yes flask db upgrade"
        )


def _print_fund_product_type_counts(conn, label):
    fund_counts = conn.execute(text(
        "SELECT product_type, COUNT(*) FROM core_funds GROUP BY product_type ORDER BY product_type"
    )).fetchall()
    class_counts = conn.execute(text(
        "SELECT product_type, COUNT(*) FROM share_classes GROUP BY product_type ORDER BY product_type"
    )).fetchall()
    currency_counts = conn.execute(text(
        "SELECT currency, COUNT(*) FROM share_classes GROUP BY currency ORDER BY currency"
    )).fetchall()

    print(f"\n==== fund/share-class product_type counts ({label}) ====")
    print(f"  core_funds:    {dict(fund_counts)}")
    print(f"  share_classes: {dict(class_counts)}")
    print(f"  currencies:    {dict(currency_counts)}")
    print("=" * (40 + len(label)))

    return {
        "core_funds": {k: v for k, v in fund_counts},
        "share_classes": {k: v for k, v in class_counts},
        "currencies": {k: v for k, v in currency_counts},
    }


def _backfill_fund_product_type(conn):
    """
    SHARES for DPRP (same match as migration 017 / is_dangote_dprp_fund),
    FUNDS for everything else; share_classes inherit from their core_fund.
    Pulled out of upgrade() so a test can exercise this exact SQL against a
    scratch set of rows instead of re-typing a copy of it.

    Assumes core_funds.product_type / share_classes.product_type already
    exist (nullable) on the target connection.
    """
    conn.execute(text("""
        UPDATE core_funds
        SET product_type = 'SHARES'
        WHERE product_type IS NULL
          AND (
              UPPER(COALESCE(fund_code, '')) = 'DPRP'
              OR LOWER(COALESCE(fund_name, '')) LIKE '%dangote%'
              OR LOWER(COALESCE(fund_name, '')) LIKE '%dprp%'
          )
    """))
    conn.execute(text("UPDATE core_funds SET product_type = 'FUNDS' WHERE product_type IS NULL"))

    conn.execute(text("""
        UPDATE share_classes sc
        SET product_type = cf.product_type
        FROM core_funds cf
        WHERE sc.core_fund_id = cf.id AND sc.product_type IS NULL
    """))
    conn.execute(text("UPDATE share_classes SET product_type = 'FUNDS' WHERE product_type IS NULL"))


def upgrade():
    _require_backup_confirmation()
    conn = op.get_bind()

    # 1. Columns — nullable for now so the backfill below can target the real
    # rows before the NOT NULL constraint is enforced. product_type_enum
    # already exists (created by migration 017).
    conn.execute(text("ALTER TABLE core_funds ADD COLUMN IF NOT EXISTS product_type product_type_enum"))
    conn.execute(text("ALTER TABLE share_classes ADD COLUMN IF NOT EXISTS product_type product_type_enum"))

    before = _print_fund_product_type_counts(conn, "before backfill")

    # 2. Backfill (see _backfill_fund_product_type).
    _backfill_fund_product_type(conn)

    # 3. Enforce NOT NULL now that every row has a value, and index both columns.
    conn.execute(text("ALTER TABLE core_funds ALTER COLUMN product_type SET NOT NULL"))
    conn.execute(text("ALTER TABLE core_funds ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    conn.execute(text("ALTER TABLE share_classes ALTER COLUMN product_type SET NOT NULL"))
    conn.execute(text("ALTER TABLE share_classes ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_core_funds_product_type ON core_funds (product_type)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_share_classes_product_type ON share_classes (product_type)"))

    # 4. Currency: widen the CHECK constraint to allow NGN, then correct
    # DPRP's own share class(es) from the Task-3-era 'USD' workaround.
    conn.execute(text("ALTER TABLE share_classes DROP CONSTRAINT IF EXISTS _currency_check"))
    conn.execute(text("ALTER TABLE share_classes ADD CONSTRAINT _currency_check CHECK (currency IN ('KES', 'USD', 'NGN'))"))
    conn.execute(text("""
        UPDATE share_classes sc
        SET currency = 'NGN'
        FROM core_funds cf
        WHERE sc.core_fund_id = cf.id AND cf.product_type = 'SHARES' AND sc.currency != 'NGN'
    """))

    after = _print_fund_product_type_counts(conn, "after backfill")

    # 5. Audit trail for this bulk assignment — one summary row, same
    # reasoning as migration 017's (a single migration-level decision, not
    # one row per fund/share-class).
    conn.execute(
        text("""
            INSERT INTO audit_logs
                (action, target_type, description, old_value, new_value, success, timestamp)
            VALUES
                (:action, :target_type, :description, :old_value, :new_value, :success, now())
        """),
        {
            "action": "FUND_PRODUCT_TYPE_MIGRATION_BACKFILL",
            "target_type": "migration",
            "description": (
                "Migration 020: backfilled product_type on core_funds and share_classes — "
                "DPRP became SHARES (and its share class currency corrected USD -> NGN), "
                "everything else FUNDS."
            ),
            "old_value": json.dumps(before),
            "new_value": json.dumps(after),
            "success": True,
        },
    )


def downgrade():
    conn = op.get_bind()

    conn.execute(text("DROP INDEX IF EXISTS ix_share_classes_product_type"))
    conn.execute(text("DROP INDEX IF EXISTS ix_core_funds_product_type"))

    # Revert the NGN correction before re-tightening the CHECK constraint —
    # Postgres refuses to add a constraint that existing rows would violate.
    conn.execute(text("""
        UPDATE share_classes sc
        SET currency = 'USD'
        FROM core_funds cf
        WHERE sc.core_fund_id = cf.id AND cf.product_type = 'SHARES' AND sc.currency = 'NGN'
    """))
    conn.execute(text("ALTER TABLE share_classes DROP CONSTRAINT IF EXISTS _currency_check"))
    conn.execute(text("ALTER TABLE share_classes ADD CONSTRAINT _currency_check CHECK (currency IN ('KES', 'USD'))"))

    conn.execute(text("ALTER TABLE share_classes DROP COLUMN IF EXISTS product_type"))
    conn.execute(text("ALTER TABLE core_funds DROP COLUMN IF EXISTS product_type"))
