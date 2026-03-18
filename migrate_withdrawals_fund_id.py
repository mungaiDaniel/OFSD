#!/usr/bin/env python
"""
Database Migration: Add missing Withdrawal columns.

Your project uses db.create_all() (no Alembic), so schema changes must be applied
manually for existing tables.

This migration adds (if missing):
- withdrawals.fund_id (int FK-like column)
- withdrawals.status (varchar)
- withdrawals.approved_at (timestamp)
- withdrawals.fund_name made nullable (if needed)
"""

import sys
from sqlalchemy import text
from app.database.database import db
from main import app


def run_migration():
    with app.app_context():
        try:
            print("=" * 70)
            print("Starting database migration: withdrawals columns")
            print("=" * 70)

            # Inspect existing columns
            existing_cols = db.session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'withdrawals'
                    """
                )
            ).fetchall()
            existing_cols = {r[0] for r in existing_cols}
            print(f"Existing columns: {sorted(existing_cols)}")

            def exec_sql(sql: str):
                print(f"SQL: {sql}")
                db.session.execute(text(sql))
                db.session.commit()
                print("OK")

            # fund_id
            if "fund_id" not in existing_cols:
                exec_sql("ALTER TABLE withdrawals ADD COLUMN fund_id INTEGER;")

            # approved_at
            if "approved_at" not in existing_cols:
                exec_sql("ALTER TABLE withdrawals ADD COLUMN approved_at TIMESTAMP NULL;")

            # status (add nullable first, backfill, then enforce)
            if "status" not in existing_cols:
                exec_sql("ALTER TABLE withdrawals ADD COLUMN status VARCHAR(20);")
                exec_sql("UPDATE withdrawals SET status = 'Pending' WHERE status IS NULL;")
                exec_sql("ALTER TABLE withdrawals ALTER COLUMN status SET DEFAULT 'Pending';")
                exec_sql("ALTER TABLE withdrawals ALTER COLUMN status SET NOT NULL;")

            # fund_name nullable (older versions required it)
            try:
                exec_sql("ALTER TABLE withdrawals ALTER COLUMN fund_name DROP NOT NULL;")
            except Exception as e:
                db.session.rollback()
                print(f"ℹ️  fund_name already nullable or column missing: {str(e)[:120]}")

            print("\nMigration completed.")
            print("Next: backfill withdrawals.fund_id for existing rows if any.")
            return True

        except Exception as e:
            print(f"\nMigration failed: {e}")
            db.session.rollback()
            return False


if __name__ == "__main__":
    ok = run_migration()
    sys.exit(0 if ok else 1)

