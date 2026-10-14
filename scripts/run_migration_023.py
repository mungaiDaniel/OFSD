"""
One-off runner for migration 023_shares_deposit_currency_usd.

Why this exists: this codebase has never actually wired up Flask-Migrate's
CLI (`Migrate(app, db)` is never called in main.py), so `flask db upgrade`
fails with "No such command 'db'" even though migrations/versions/*.py files
exist and are written as real Alembic scripts. Most of those scripts'
changes (020-022) are also duplicated as plain idempotent SQL directly in
main.py's create_app(), so they apply automatically on every app restart —
no separate step needed for those.

Migration 023 is the one exception: a genuine one-time data relabel (SHARES
deposits mislabelled 'NGN' instead of 'USD') that is NOT duplicated in
main.py's startup sync. This script runs that same logic directly, using a
plain SQLAlchemy connection instead of Alembic's `op` (which only works
inside a real Alembic migration context) — same idempotency/backup checks
as the migration file, plus a fix the migration file itself was missing:
its audit-log INSERT didn't set date_created/date_updated/created_by/active,
which are all NOT NULL with only Python-side (ORM) defaults, so the raw SQL
INSERT would fail every time it was actually run. Fixed here and in the
migration file itself.

Usage (from the backend directory, with the venv active):
    OFSD_CONFIRM_BACKUP=yes python scripts/run_migration_023.py

Safe to run more than once — it checks for its own audit-log marker first
and does nothing if migration 023 has already been applied.
"""

import os
import sys
from sqlalchemy import text

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import main
from app.database.database import db

MARKER_ACTION = "SHARES_DEPOSIT_CURRENCY_USD"


def run():
    app = main.app
    with app.app_context():
        conn = db.session.connection()

        already_done = conn.execute(
            text("SELECT 1 FROM audit_logs WHERE action = :a LIMIT 1"), {"a": MARKER_ACTION}
        ).first()
        if already_done:
            print("023: SHARES deposit currency already corrected (audit marker present) - skipping.")
            return

        if os.environ.get("OFSD_CONFIRM_BACKUP", "").strip().lower() not in ("yes", "true", "1"):
            raise RuntimeError(
                "Refusing to run migration 023 without a confirmed backup.\n"
                "It relabels DPRP share classes and deposits from NGN to USD (labels only).\n"
                "Take a database backup, then re-run with OFSD_CONFIRM_BACKUP=yes set."
            )

        classes = conn.execute(text("""
            UPDATE share_classes sc SET currency = 'USD'
            FROM core_funds cf
            WHERE sc.core_fund_id = cf.id AND cf.product_type = 'SHARES' AND sc.currency = 'NGN'
        """)).rowcount
        deposits = conn.execute(text("""
            UPDATE investments SET currency_type = 'USD'
            WHERE product_type = 'SHARES' AND currency_type = 'NGN'
        """)).rowcount
        print(f"023: {classes} SHARES share class(es) and {deposits} deposit(s) relabelled NGN -> USD")

        conn.execute(
            text("""
                INSERT INTO audit_logs (action, target_type, description, success, timestamp, date_created, date_updated, created_by, active)
                VALUES (:action, 'migration', :description, true, now(), now(), now(), 'SYSTEM', true)
            """),
            {
                "action": MARKER_ACTION,
                "description": (
                    f"Migration 023: SHARES deposits are USD - relabelled {classes} share class(es) "
                    f"and {deposits} deposit(s) from NGN to USD (labels only, no amounts changed)."
                ),
            },
        )
        db.session.commit()
        print("023: committed.")


if __name__ == "__main__":
    run()
