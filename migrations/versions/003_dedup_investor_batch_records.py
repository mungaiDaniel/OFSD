"""
003_dedup_investor_batch_records.py
====================================
Migration: Remove duplicate (internal_client_code, batch_id) rows from
the investments table.

Business Rule:
    Each investor may only have ONE record per Batch ID.
    Duplicate rows inflate the valuation pool and the investor row count.

Strategy:
    For every (internal_client_code, batch_id) pair that appears more than
    once, keep the row with the lowest `id` (earliest insert) and DELETE the
    rest.  All deleted rows are printed to stdout for audit purposes.

Usage (standalone — does NOT require Alembic):
    cd backend
    python migrations/versions/003_dedup_investor_batch_records.py

Usage (via Flask app context):
    from migrations.versions.003_dedup_investor_batch_records import run_migration
    run_migration(db.session)
"""

from __future__ import annotations

import sys
import os

# ---------------------------------------------------------------------------
# Allow running as a standalone script from the backend/ directory
# ---------------------------------------------------------------------------
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def run_migration(session) -> dict:
    """
    Find and delete duplicate (internal_client_code, batch_id) investment rows.

    Returns a summary dict:
        {
            "duplicate_pairs_found": int,
            "rows_deleted": int,
            "deleted_ids": list[int],
        }
    """
    from sqlalchemy import text

    print("=" * 60)
    print("MIGRATION 003 — Dedup investor_batch_records")
    print("=" * 60)

    # Step 1: Find all (internal_client_code, batch_id) pairs with > 1 row
    dupe_query = text("""
        SELECT internal_client_code, batch_id, COUNT(*) AS cnt
        FROM investments
        WHERE batch_id IS NOT NULL
        GROUP BY internal_client_code, batch_id
        HAVING COUNT(*) > 1
    """)

    dupe_pairs = session.execute(dupe_query).fetchall()

    if not dupe_pairs:
        print("✅ No duplicate (internal_client_code, batch_id) pairs found. Nothing to do.")
        return {"duplicate_pairs_found": 0, "rows_deleted": 0, "deleted_ids": []}

    print(f"\n⚠  Found {len(dupe_pairs)} duplicate pair(s):\n")

    all_deleted_ids: list[int] = []

    for row in dupe_pairs:
        code = row[0]
        batch_id = row[1]
        count = row[2]

        # Step 2: For each duplicate pair, get all matching IDs ordered oldest first
        rows_query = text("""
            SELECT id, investor_name, amount_deposited, date_deposited
            FROM investments
            WHERE internal_client_code = :code
              AND batch_id = :batch_id
            ORDER BY id ASC
        """)
        matching_rows = session.execute(rows_query, {"code": code, "batch_id": batch_id}).fetchall()

        keeper_id = matching_rows[0][0]
        keeper_name = matching_rows[0][1]
        to_delete = [r[0] for r in matching_rows[1:]]

        print(f"  Pair  : internal_client_code={code!r}, batch_id={batch_id}")
        print(f"  Count : {count} rows")
        print(f"  Keep  : id={keeper_id} ({keeper_name})")
        print(f"  Delete: ids={to_delete}")

        for deleted_id in to_delete:
            row_info_q = text("""
                SELECT investor_name, investor_email, amount_deposited, date_deposited
                FROM investments WHERE id = :id
            """)
            row_info = session.execute(row_info_q, {"id": deleted_id}).fetchone()
            if row_info:
                print(f"    🗑  Deleting id={deleted_id}: {row_info[0]} ({row_info[1]}) "
                      f"amount={row_info[2]} deposited={row_info[3]}")

        # Step 3: Delete the duplicate rows (keep lowest id = oldest record)
        delete_query = text("""
            DELETE FROM investments
            WHERE internal_client_code = :code
              AND batch_id = :batch_id
              AND id <> :keeper_id
        """)
        result = session.execute(delete_query, {
            "code": code,
            "batch_id": batch_id,
            "keeper_id": keeper_id,
        })

        deleted_count = result.rowcount
        all_deleted_ids.extend(to_delete)
        print(f"  ✅ Deleted {deleted_count} row(s) for pair ({code!r}, {batch_id})\n")

    # Step 4: Commit
    session.commit()

    summary = {
        "duplicate_pairs_found": len(dupe_pairs),
        "rows_deleted": len(all_deleted_ids),
        "deleted_ids": all_deleted_ids,
    }

    print("=" * 60)
    print(f"MIGRATION 003 COMPLETE")
    print(f"  Duplicate pairs found : {summary['duplicate_pairs_found']}")
    print(f"  Total rows deleted    : {summary['rows_deleted']}")
    print(f"  Deleted IDs           : {summary['deleted_ids']}")
    print("=" * 60)

    return summary


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Bootstrap the Flask app so we get a real DB session
    from main import app  # noqa: E402  (main.py is in backend/)
    from app.database.database import db  # noqa: E402

    with app.app_context():
        summary = run_migration(db.session)
        if summary["rows_deleted"] == 0:
            sys.exit(0)
        print(f"\nDone. {summary['rows_deleted']} orphaned row(s) removed.")
