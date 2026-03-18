#!/usr/bin/env python
"""Database migration script to make certificate_number nullable in batches table."""

import sys
from sqlalchemy import text
from app.database.database import db
from main import app

def run_migration():
    """Execute the migration to make certificate_number nullable."""
    with app.app_context():
        try:
            # Execute the migration to alter column to nullable
            db.session.execute(
                text("ALTER TABLE batches ALTER COLUMN certificate_number DROP NOT NULL")
            )
            db.session.commit()
            print("✅ Migration completed successfully: certificate_number column is now nullable")
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
