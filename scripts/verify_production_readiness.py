"""Production Readiness & Schema Verification Script

Verifies all 30 database tables, required columns, and active admin users.
Usage:
    python scripts/verify_production_readiness.py
"""

import os
import sys

# Ensure root folder is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import main
from app.database.database import db
from sqlalchemy import inspect
from app.Admin.model import User
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass


def verify_database():
    app = main.app
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        expected_tables = sorted(db.metadata.tables.keys())
        print(f"\n==================================================")
        print(f" OFSD PRODUCTION DATABASE READINESS VERIFICATION ")
        print(f"==================================================")
        print(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")

        all_ok = True

        # 1. Table Verification
        missing_tables = []
        for t in expected_tables:
            if t not in existing_tables:
                missing_tables.append(t)

        if missing_tables:
            all_ok = False
            print(f"[FAIL] Missing {len(missing_tables)} tables:")
            for mt in missing_tables:
                print(f"   ❌ {mt}")
        else:
            print(f"[PASS] All {len(expected_tables)} tables exist in the database.")

        # 2. Critical Columns Verification
        critical_checks = {
            "batches": [
                "share_class_id", "is_open", "auto_close_at", "total_shares",
                "deployment_nav", "deployment_total_nav", "deployment_date_actual",
                "transfer_transaction_cost", "cached_total_capital", "is_oversubscribed", "allocation_rate"
            ],
            "investments": [
                "share_class_id", "deposit_date", "shares_owned", "currency_type",
                "original_deposit_amount", "current_market_value", "opening_market_value",
                "rounding_adjustment", "official_receipt_value", "oversubscription_refund_amount"
            ],
            "withdrawals": ["source", "oversubscription_notice_sent_at"],
            "pending_emails": ["currency_type", "trigger_source", "queued_at", "statement_fund_ids"],
            "email_logs": ["trigger_source"],
            "audit_logs": ["user_email", "user_name"],
            "user": ["role", "status"],
            "share_classes": ["current_nav"]
        }

        print("\n--- Column Verifications ---")
        for table, cols in critical_checks.items():
            if table not in existing_tables:
                continue
            table_cols = {c["name"] for c in inspector.get_columns(table)}
            missing_cols = [c for c in cols if c not in table_cols]
            if missing_cols:
                all_ok = False
                print(f"[FAIL] Table '{table}' missing columns: {missing_cols}")
            else:
                print(f"[PASS] Table '{table}' has all {len(cols)} required columns.")

        # 3. User & Auth Verification
        print("\n--- User & Authorization Status ---")
        try:
            users = db.session.query(User).all()
            if not users:
                print("[WARN] No users found in database! Run create_super.py to create one.")
            else:
                print(f"Found {len(users)} users:")
                active_admins = 0
                for u in users:
                    status = getattr(u, "status", "unknown")
                    role = getattr(u, "role", "unknown")
                    is_active = (status == "active")
                    print(f"   {'✓' if is_active else '❌'} {u.email} (Role: {role}, Status: {status})")
                    if is_active and role in ("admin", "super_admin"):
                        active_admins += 1
                if active_admins == 0:
                    all_ok = False
                    print("[FAIL] No active admin/super_admin found! Run migration 016 or activate user.")
                else:
                    print(f"[PASS] {active_admins} active admin(s) ready to log in.")
        except Exception as e:
            all_ok = False
            print(f"[FAIL] Failed querying users: {e}")

        # 4. Core Funds & Share Classes
        print("\n--- Fund Architecture Status ---")
        try:
            funds = db.session.query(CoreFund).all()
            classes = db.session.query(ShareClass).all()
            print(f"Core Funds: {len(funds)} | Share Classes: {len(classes)}")
            for f in funds:
                f_classes = [c.class_code for c in classes if c.core_fund_id == f.id]
                print(f"   • Fund: {f.fund_name} (Classes: {', '.join(f_classes) if f_classes else 'None'})")
        except Exception as e:
            print(f"[WARN] Funds check note: {e}")

        print("\n==================================================")
        if all_ok:
            print(" RESULT: 100% PRODUCTION READY! All checks passed.")
        else:
            print(" RESULT: ISSUES DETECTED. Run python migrate_all.py")
        print("==================================================\n")


if __name__ == "__main__":
    verify_database()
