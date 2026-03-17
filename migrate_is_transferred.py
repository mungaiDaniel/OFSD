#!/usr/bin/env python
"""Database migration script to add is_transferred column to batches table."""

import sys
from sqlalchemy import text
from app.database.database import db
from main import app

def run_migration():
    """Execute the migration to add is_transferred column."""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(
                text("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'batches' 
                        AND column_name = 'is_transferred'
                    )
                """)
            )
            
            column_exists = result.scalar()
            
            if column_exists:
                print("Column 'is_transferred' already exists in batches table.")
                return True
            
            # Execute the migration
            db.session.execute(
                text("ALTER TABLE batches ADD COLUMN is_transferred BOOLEAN DEFAULT FALSE")
            )
            db.session.commit()
            print("✅ Migration completed successfully: Added 'is_transferred' column to batches table")
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
