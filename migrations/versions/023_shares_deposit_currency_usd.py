"""SHARES (DPRP) deposits are USD: set share classes back to USD, relabel deposits

Revision ID: 023_shares_deposit_currency_usd
Revises: 022_add_core_fund_description
Create Date: 2026-10-08

DPRP deposits are taken in USD; deployment (app/logic/shares_deployment_service.py)
converts them to NGN shares. Migration 020 set DPRP's share class currency to
NGN, which made every new DPRP deposit carry currency_type = 'NGN' even though
the amounts are USD. ShareClass.currency now means the deposit currency, and
ShareClass.valuation_currency (always NGN for SHARES) covers the NAV side.

This migration, once:
  * sets every SHARES share class with currency 'NGN' to 'USD';
  * relabels SHARES deposits with currency_type 'NGN' to 'USD'.
Labels only — no amounts, shares, NAVs or refunds change.

main.py's startup sync used to force SHARES classes to NGN on every start; it
no longer does. This writes a SHARES_DEPOSIT_CURRENCY_USD audit row and skips
if one exists, so it never runs twice (and never undoes a later deliberate
change of a class back to NGN).

SAFETY: requires OFSD_CONFIRM_BACKUP=yes, same as migration 020.
"""

import os

from alembic import op
from sqlalchemy import text

revision = "023_shares_deposit_currency_usd"
down_revision = "022_add_core_fund_description"
branch_labels = None
depends_on = None

MARKER_ACTION = "SHARES_DEPOSIT_CURRENCY_USD"


def upgrade():
    conn = op.get_bind()
    already_done = conn.execute(
        text("SELECT 1 FROM audit_logs WHERE action = :a LIMIT 1"), {"a": MARKER_ACTION}
    ).first()
    if already_done:
        print("023: SHARES deposit currency already corrected (audit marker present) - skipping.")
        return

    if os.environ.get("OFSD_CONFIRM_BACKUP", "").strip().lower() not in ("yes", "true", "1"):
        raise RuntimeError(
            "Refusing to run migration 023_shares_deposit_currency_usd without a confirmed backup.\n"
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
            INSERT INTO audit_logs (action, target_type, description, success, timestamp)
            VALUES (:action, 'migration', :description, true, now())
        """),
        {
            "action": MARKER_ACTION,
            "description": (
                f"Migration 023: SHARES deposits are USD - relabelled {classes} share class(es) "
                f"and {deposits} deposit(s) from NGN to USD (labels only, no amounts changed)."
            ),
        },
    )


def downgrade():
    # Labels only; a later edit may have legitimately set a class to NGN again,
    # so blindly flipping USD back would be wrong. Intentionally a no-op.
    pass
