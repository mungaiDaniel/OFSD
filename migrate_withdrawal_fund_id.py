#!/usr/bin/env python3
"""
Migration Script: Add fund_id column to withdrawals table
Date: March 17, 2026

This script adds the missing fund_id column to the withdrawals table
to support multi-fund withdrawal tracking.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database.database import db
from app import create_app


def run_migration():
    """Execute the migration"""
    app = create_app()
    
    with app.app_context():
        try:
            print("=" * 80)
            print("Migration: Add fund_id column to withdrawals table")
            print("=" * 80)
            
            # SQL to add the fund_id column with default value of 1 (Axiom)
            # This handles existing data gracefully
            sql_add_column = """
            ALTER TABLE withdrawals
            ADD COLUMN IF NOT EXISTS fund_id INTEGER;
            """
            
            # SQL to set default values for existing rows (if fund_id is NULL)
            # Default to fund_id = 1 (assumes first core fund is the default)
            sql_set_defaults = """
            UPDATE withdrawals
            SET fund_id = 1
            WHERE fund_id IS NULL;
            """
            
            # SQL to add foreign key constraint
            sql_add_fk = """
            ALTER TABLE withdrawals
            ADD CONSTRAINT fk_withdrawals_core_funds
            FOREIGN KEY (fund_id) REFERENCES core_funds(id)
            ON DELETE RESTRICT
            ON UPDATE CASCADE;
            """
            
            # SQL to add index
            sql_add_index = """
            CREATE INDEX IF NOT EXISTS ix_withdrawals_code_fund_date
            ON withdrawals (internal_client_code, fund_id, date_withdrawn);
            """
            
            # SQL to alter column to NOT NULL (after data is populated)
            sql_not_null = """
            ALTER TABLE withdrawals
            ALTER COLUMN fund_id SET NOT NULL;
            """
            
            print("\n[1] Adding fund_id column...")
            db.session.execute(db.text(sql_add_column))
            db.session.commit()
            print("    ✓ fund_id column added")
            
            print("\n[2] Setting default values for existing rows...")
            db.session.execute(db.text(sql_set_defaults))
            db.session.commit()
            print("    ✓ Default values set (fund_id = 1 for all existing rows)")
            
            print("\n[3] Adding NOT NULL constraint...")
            db.session.execute(db.text(sql_not_null))
            db.session.commit()
            print("    ✓ NOT NULL constraint applied")
            
            print("\n[4] Adding foreign key constraint...")
            try:
                db.session.execute(db.text(sql_add_fk))
                db.session.commit()
                print("    ✓ Foreign key constraint added")
            except Exception as fk_error:
                print(f"    ⚠ Could not add FK (may already exist): {str(fk_error)}")
                db.session.rollback()
            
            print("\n[5] Adding/ensuring index...")
            db.session.execute(db.text(sql_add_index))
            db.session.commit()
            print("    ✓ Index created/verified")
            
            print("\n" + "=" * 80)
            print("✓ Migration completed successfully!")
            print("=" * 80)
            
            # Verify the migration
            print("\n[VERIFICATION] Checking withdrawals table structure...")
            check_sql = """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'withdrawals'
            ORDER BY ordinal_position;
            """
            result = db.session.execute(db.text(check_sql)).fetchall()
            print(f"\nColumns in withdrawals table:")
            print(f"{'Column':<25} {'Type':<15} {'Nullable':<10}")
            print("-" * 50)
            for row in result:
                nullable = "NO" if row[2] == False else "YES"
                print(f"{row[0]:<25} {row[1]:<15} {nullable:<10}")
            
            print("\n✓ Verification complete!")
            
        except Exception as e:
            print(f"\n✗ Migration failed: {str(e)}")
            db.session.rollback()
            sys.exit(1)


if __name__ == '__main__':
    run_migration()
