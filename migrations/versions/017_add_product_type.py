"""Separate SHARES (DPRP) from FUNDS batches/deposits via product_type

Revision ID: 017_add_product_type
Revises: 016_complete_production_schema_sync
Create Date: 2026-10-07

Adds a product_type ('FUNDS'|'SHARES') column to batches and investments.
Every existing batch/investment belonging to DPRP (Dangote Petroleum Refinery
and Petrochemicals — identified the same way as everywhere else in this
codebase, see app.utils.statement_theme.is_dangote_dprp_fund) is backfilled to
SHARES; everything else becomes FUNDS. No IDs, amounts, shares, NAV history or
audit records are touched — this only adds and backfills the new column.

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

revision = "017_add_product_type"
down_revision = "016_complete_production_schema_sync"
branch_labels = None
depends_on = None


def _require_backup_confirmation():
    if os.environ.get("OFSD_CONFIRM_BACKUP", "").strip().lower() not in ("yes", "true", "1"):
        raise RuntimeError(
            "Refusing to run migration 017_add_product_type without a confirmed backup.\n"
            "This migration backfills product_type on every row of batches and investments.\n"
            "Take a database backup, then re-run with OFSD_CONFIRM_BACKUP=yes set, e.g.:\n"
            "  pg_dump \"$DATABASE_URL\" -Fc -f pre_017_product_type_backup.dump\n"
            "  OFSD_CONFIRM_BACKUP=yes flask db upgrade"
        )


def _print_product_type_counts(conn, label):
    batch_counts = conn.execute(text(
        "SELECT product_type, COUNT(*) FROM batches GROUP BY product_type ORDER BY product_type"
    )).fetchall()
    investment_counts = conn.execute(text(
        "SELECT product_type, COUNT(*) FROM investments GROUP BY product_type ORDER BY product_type"
    )).fetchall()
    investor_counts = conn.execute(text(
        "SELECT product_type, COUNT(DISTINCT internal_client_code) FROM investments "
        "GROUP BY product_type ORDER BY product_type"
    )).fetchall()

    print(f"\n==== product_type counts ({label}) ====")
    print(f"  batches:     {dict(batch_counts)}")
    print(f"  investments: {dict(investment_counts)}")
    print(f"  investors:   {dict(investor_counts)}  (an investor holding both products counts in both)")
    print("=" * (26 + len(label)))

    return {
        "batches": {k: v for k, v in batch_counts},
        "investments": {k: v for k, v in investment_counts},
        "investors": {k: v for k, v in investor_counts},
    }


def _backfill_product_type(conn):
    """
    The actual backfill logic: SHARES for DPRP (by fund code 'DPRP' or name
    containing 'dangote'/'dprp' — the exact match used by
    is_dangote_dprp_fund), FUNDS for everything else. Investments inherit from
    their batch. Pulled out of upgrade() so a test can exercise this exact SQL
    against a scratch set of rows instead of re-typing a copy of it.

    Assumes batches.product_type / investments.product_type already exist
    (nullable) on the target connection.
    """
    # Batches: SHARES for DPRP, FUNDS for everything else (including batches
    # with no investments/fund resolved yet).
    conn.execute(text("""
        UPDATE batches b
        SET product_type = 'SHARES'
        FROM share_classes sc
        JOIN core_funds cf ON cf.id = sc.core_fund_id
        WHERE b.share_class_id = sc.id
          AND (
              UPPER(COALESCE(cf.fund_code, '')) = 'DPRP'
              OR LOWER(COALESCE(cf.fund_name, '')) LIKE '%dangote%'
              OR LOWER(COALESCE(cf.fund_name, '')) LIKE '%dprp%'
          )
    """))
    conn.execute(text("""
        UPDATE batches
        SET product_type = 'FUNDS'
        WHERE product_type IS NULL
    """))

    # Investments: every deposit/holding inherits its batch's product_type
    # (same rule enforced going forward by the ORM-level before_insert event on
    # Investment — see app/Investments/model.py). A handful of legacy
    # investments may also be directly resolvable to DPRP via fund_id/fund_name
    # even if their batch predates share_class_id/DPRP tagging; cover that case
    # too so no DPRP deposit is missed.
    conn.execute(text("""
        UPDATE investments i
        SET product_type = b.product_type
        FROM batches b
        WHERE i.batch_id = b.id
    """))
    conn.execute(text("""
        UPDATE investments i
        SET product_type = 'SHARES'
        FROM core_funds cf
        WHERE i.fund_id = cf.id
          AND i.product_type = 'FUNDS'
          AND (
              UPPER(COALESCE(cf.fund_code, '')) = 'DPRP'
              OR LOWER(COALESCE(cf.fund_name, '')) LIKE '%dangote%'
              OR LOWER(COALESCE(cf.fund_name, '')) LIKE '%dprp%'
          )
    """))
    conn.execute(text("""
        UPDATE investments
        SET product_type = 'FUNDS'
        WHERE product_type IS NULL
    """))


def upgrade():
    _require_backup_confirmation()
    conn = op.get_bind()

    # 1. Enum type (idempotent — mirrors the currency_type_enum pattern in 016).
    conn.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'product_type_enum') THEN
                CREATE TYPE product_type_enum AS ENUM ('FUNDS', 'SHARES');
            END IF;
        END $$;
    """))

    # 2. Columns — nullable for now so the backfill below can target the real
    # rows before the NOT NULL constraint is enforced.
    conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS product_type product_type_enum"))
    conn.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS product_type product_type_enum"))

    before = _print_product_type_counts(conn, "before backfill")

    # 3. Backfill (see _backfill_product_type).
    _backfill_product_type(conn)

    # 4. Enforce NOT NULL now that every row has a value, and index both columns.
    conn.execute(text("ALTER TABLE batches ALTER COLUMN product_type SET NOT NULL"))
    conn.execute(text("ALTER TABLE batches ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    conn.execute(text("ALTER TABLE investments ALTER COLUMN product_type SET NOT NULL"))
    conn.execute(text("ALTER TABLE investments ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_batches_product_type ON batches (product_type)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_product_type ON investments (product_type)"))

    after = _print_product_type_counts(conn, "after backfill")

    # 5. Audit trail for this bulk assignment. One summary row (not one per
    # batch/investment — this is a single migration-level decision, and at
    # production row counts a per-row audit entry here would itself be a
    # second, slower data migration) recording exactly what every row was
    # assigned and why, per-batch assignments are visible via each batch's
    # product_type going forward, and any batch/investment created by the API
    # from this point on gets its own BATCH_PRODUCT_TYPE_ASSIGNED audit entry
    # (see app.Batch.controllers.BatchController.create_batch).
    conn.execute(
        text("""
            INSERT INTO audit_logs
                (action, target_type, description, old_value, new_value, success, timestamp)
            VALUES
                (:action, :target_type, :description, :old_value, :new_value, :success, now())
        """),
        {
            "action": "PRODUCT_TYPE_MIGRATION_BACKFILL",
            "target_type": "migration",
            "description": (
                "Migration 017: backfilled product_type on batches and investments — "
                "DPRP rows became SHARES, everything else FUNDS."
            ),
            "old_value": json.dumps(before),
            "new_value": json.dumps(after),
            "success": True,
        },
    )


def downgrade():
    conn = op.get_bind()

    conn.execute(text("DROP INDEX IF EXISTS ix_investments_product_type"))
    conn.execute(text("DROP INDEX IF EXISTS ix_batches_product_type"))

    conn.execute(text("ALTER TABLE investments DROP COLUMN IF EXISTS product_type"))
    conn.execute(text("ALTER TABLE batches DROP COLUMN IF EXISTS product_type"))

    conn.execute(text("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'product_type_enum') THEN
                DROP TYPE product_type_enum;
            END IF;
        END $$;
    """))
