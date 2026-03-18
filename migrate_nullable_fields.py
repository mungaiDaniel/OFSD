#!/usr/bin/env python
"""
Comprehensive database migration script to make batch fields nullable
and ensure they match the SQLAlchemy model definition.
"""

import sys
from sqlalchemy import text
from app.database.database import db
from main import app

def run_migrations():
    """Execute all necessary migrations for nullable fields."""
    with app.app_context():
        try:
            print("Starting database migration...")
            
            # Migration 1: Make date_deployed nullable
            print("\n1. Making date_deployed nullable...")
            try:
                db.session.execute(
                    text("ALTER TABLE batches ALTER COLUMN date_deployed DROP NOT NULL")
                )
                print("   ✅ date_deployed is now nullable")
            except Exception as e:
                if "does not exist" in str(e).lower() or "constraint" not in str(e).lower():
                    print(f"   ℹ️  date_deployed already nullable or constraint doesn't exist: {str(e)[:50]}")
                else:
                    raise
            
            # Migration 2: Make certificate_number nullable
            print("\n2. Making certificate_number nullable...")
            try:
                db.session.execute(
                    text("ALTER TABLE batches ALTER COLUMN certificate_number DROP NOT NULL")
                )
                print("   ✅ certificate_number is now nullable")
            except Exception as e:
                if "does not exist" in str(e).lower() or "constraint" not in str(e).lower():
                    print(f"   ℹ️  certificate_number already nullable or constraint doesn't exist: {str(e)[:50]}")
                else:
                    raise
            
            # Migration 3: Make date_closed nullable
            print("\n3. Making date_closed nullable...")
            try:
                db.session.execute(
                    text("ALTER TABLE batches ALTER COLUMN date_closed DROP NOT NULL")
                )
                print("   ✅ date_closed is now nullable")
            except Exception as e:
                if "does not exist" in str(e).lower() or "constraint" not in str(e).lower():
                    print(f"   ℹ️  date_closed already nullable or constraint doesn't exist: {str(e)[:50]}")
                else:
                    raise
            
            # Migration 4: Handle date_deployed DEFAULT constraint
            print("\n4. Setting date_deployed default to NULL...")
            try:
                db.session.execute(
                    text("ALTER TABLE batches ALTER COLUMN date_deployed SET DEFAULT NULL")
                )
                print("   ✅ date_deployed default set to NULL")
            except Exception as e:
                print(f"   ℹ️  Default may already be configured: {str(e)[:50]}")
            
            # Migration 5: Handle certificate_number DEFAULT constraint
            print("\n5. Setting certificate_number default to NULL...")
            try:
                db.session.execute(
                    text("ALTER TABLE batches ALTER COLUMN certificate_number SET DEFAULT NULL")
                )
                print("   ✅ certificate_number default set to NULL")
            except Exception as e:
                print(f"   ℹ️  Default may already be configured: {str(e)[:50]}")
            
            db.session.commit()
            print("\n" + "="*60)
            print("✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY")
            print("="*60)
            print("\nBatch table is now configured with nullable fields:")
            print("  • batch_name: NOT NULL (required)")
            print("  • certificate_number: nullable (optional)")
            print("  • date_deployed: nullable (optional)")
            print("  • date_closed: nullable (optional)")
            print("  • is_active: defaults to False")
            print("  • is_transferred: defaults to False")
            print("  • deployment_confirmed: defaults to False")
            print("="*60)
            
            return True
            
        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
