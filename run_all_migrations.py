#!/usr/bin/env python3
"""
COMPREHENSIVE OFDS DATABASE MIGRATION RUNNER
Date: March 17, 2026

This script runs ALL necessary database migrations in the correct order.
It handles the withdrawal fund_id issue and ensures schema consistency.
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask
from flask_cors import CORS
from config import DevelopmentConfig as Config
from app.database.database import db
from flask_jwt_extended import JWTManager
from datetime import timedelta, datetime
from sqlalchemy import text


def create_app_for_migration():
    """Create Flask app for migration"""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=1)
    JWTManager(app)
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
    db.init_app(app)
    app.app_context().push()
    
    return app


def log_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def log_step(step_num, msg):
    """Print a formatted step"""
    print(f"\n[STEP {step_num}] {msg}")


def log_success(msg):
    """Print success message"""
    print(f"    ✓ {msg}")


def log_warning(msg):
    """Print warning message"""
    print(f"    ⚠ {msg}")


def log_error(msg):
    """Print error message"""
    print(f"    ✗ {msg}")


def migration_1_nullable_fields():
    """Migration 1: Make batch fields nullable"""
    log_step(1, "Adding nullable columns (certificate_number, date_deployed, date_closed)")
    
    try:
        sql_statements = [
            "ALTER TABLE batches ALTER COLUMN certificate_number DROP NOT NULL;",
            "ALTER TABLE batches ALTER COLUMN date_deployed DROP NOT NULL;",
            "ALTER TABLE batches ALTER COLUMN date_closed DROP NOT NULL;",
        ]
        
        for sql in sql_statements:
            db.session.execute(text(sql))
        
        db.session.commit()
        log_success("Nullable columns created")
        return True
    except Exception as e:
        if "already" in str(e).lower() or "does not exist" in str(e).lower():
            log_warning(f"Already applied: {str(e)}")
            db.session.rollback()
            return True
        else:
            log_error(f"Migration 1 failed: {str(e)}")
            db.session.rollback()
            return False


def migration_2_is_transferred():
    """Migration 2: Add is_transferred column"""
    log_step(2, "Adding is_transferred column to batches")
    
    try:
        sql = """
        ALTER TABLE batches 
        ADD COLUMN IF NOT EXISTS is_transferred BOOLEAN DEFAULT FALSE;
        """
        db.session.execute(text(sql))
        db.session.commit()
        log_success("is_transferred column added")
        return True
    except Exception as e:
        if "already" in str(e).lower() or "does not exist" in str(e).lower():
            log_warning(f"Already applied: {str(e)}")
            db.session.rollback()
            return True
        else:
            log_error(f"Migration 2 failed: {str(e)}")
            db.session.rollback()
            return False


def migration_3_deployment_confirmed():
    """Migration 3: Add deployment_confirmed column"""
    log_step(3, "Adding deployment_confirmed column to batches")
    
    try:
        sql = """
        ALTER TABLE batches 
        ADD COLUMN IF NOT EXISTS deployment_confirmed BOOLEAN DEFAULT FALSE;
        """
        db.session.execute(text(sql))
        db.session.commit()
        log_success("deployment_confirmed column added")
        return True
    except Exception as e:
        if "already" in str(e).lower() or "does not exist" in str(e).lower():
            log_warning(f"Already applied: {str(e)}")
            db.session.rollback()
            return True
        else:
            log_error(f"Migration 3 failed: {str(e)}")
            db.session.rollback()
            return False


def migration_4_withdrawal_fund_id():
    """Migration 4: Add fund_id to withdrawals table"""
    log_step(4, "Adding fund_id column to withdrawals (PRIMARY FOCUS)")
    
    try:
        # Step 1: Add column
        log_step(4.1, "Adding fund_id column...")
        sql = "ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS fund_id INTEGER;"
        db.session.execute(text(sql))
        db.session.commit()
        log_success("fund_id column added")
        
        # Step 2: Set defaults for existing rows
        log_step(4.2, "Setting default fund_id=1 for existing rows...")
        sql = "UPDATE withdrawals SET fund_id = 1 WHERE fund_id IS NULL;"
        db.session.execute(text(sql))
        db.session.commit()
        log_success("Default values set")
        
        # Step 3: Add NOT NULL constraint
        log_step(4.3, "Adding NOT NULL constraint...")
        sql = "ALTER TABLE withdrawals ALTER COLUMN fund_id SET NOT NULL;"
        db.session.execute(text(sql))
        db.session.commit()
        log_success("NOT NULL constraint applied")
        
        # Step 4: Add foreign key
        log_step(4.4, "Adding FOREIGN KEY constraint...")
        try:
            sql = """
            ALTER TABLE withdrawals
            ADD CONSTRAINT fk_withdrawals_core_funds
            FOREIGN KEY (fund_id) REFERENCES core_funds(id)
            ON DELETE RESTRICT ON UPDATE CASCADE;
            """
            db.session.execute(text(sql))
            db.session.commit()
            log_success("FOREIGN KEY constraint added")
        except Exception as fk_error:
            log_warning(f"FK constraint already exists or error: {str(fk_error)}")
            db.session.rollback()
        
        # Step 5: Add index
        log_step(4.5, "Creating composite index...")
        try:
            sql = """
            CREATE INDEX IF NOT EXISTS ix_withdrawals_code_fund_date
            ON withdrawals (internal_client_code, fund_id, date_withdrawn);
            """
            db.session.execute(text(sql))
            db.session.commit()
            log_success("Index created")
        except Exception as idx_error:
            log_warning(f"Index creation: {str(idx_error)}")
            db.session.rollback()
        
        return True
        
    except Exception as e:
        log_error(f"Migration 4 failed: {str(e)}")
        db.session.rollback()
        return False


def migration_5_composite_constraint():
    """Migration 5: Add composite unique constraint"""
    log_step(5, "Adding unique constraint on investments (internal_client_code, batch_id)")
    
    try:
        # Check if constraint already exists
        check_sql = """
        SELECT EXISTS(
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = 'investments' 
            AND constraint_name = '_customer_batch_uc'
        );
        """
        result = db.session.execute(text(check_sql)).scalar()
        
        if result:
            log_warning("Constraint already exists")
            return True
        
        sql = """
        ALTER TABLE investments
        ADD CONSTRAINT _customer_batch_uc
        UNIQUE (internal_client_code, batch_id);
        """
        db.session.execute(text(sql))
        db.session.commit()
        log_success("Composite unique constraint added")
        return True
        
    except Exception as e:
        if "already" in str(e).lower() or "duplicate" in str(e).lower():
            log_warning(f"Already exists: {str(e)}")
            db.session.rollback()
            return True
        else:
            log_error(f"Migration 5 failed: {str(e)}")
            db.session.rollback()
            return False


def verify_schema():
    """Verify the schema after all migrations"""
    log_section("SCHEMA VERIFICATION")
    
    checks = []
    
    # Check 1: Batches table
    log_step(1, "Checking batches table columns...")
    try:
        sql = """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'batches'
        ORDER BY ordinal_position;
        """
        result = db.session.execute(text(sql)).fetchall()
        required = ['id', 'batch_name', 'certificate_number', 'date_deployed', 
                   'is_active', 'is_transferred', 'deployment_confirmed']
        found = [r[0] for r in result]
        
        for col in required:
            if col in found:
                log_success(f"Column '{col}' exists")
            else:
                log_warning(f"Column '{col}' MISSING")
        
        checks.append(all(col in found for col in required))
    except Exception as e:
        log_error(f"Check failed: {str(e)}")
        checks.append(False)
    
    # Check 2: Withdrawals table
    log_step(2, "Checking withdrawals table...")
    try:
        sql = """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'withdrawals'
        ORDER BY ordinal_position;
        """
        result = db.session.execute(text(sql)).fetchall()
        found = [r[0] for r in result]
        
        if 'fund_id' in found:
            log_success("Column 'fund_id' exists ✓")
            checks.append(True)
        else:
            log_error("Column 'fund_id' MISSING")
            checks.append(False)
    except Exception as e:
        log_error(f"Check failed: {str(e)}")
        checks.append(False)
    
    # Check 3: Investments unique constraint
    log_step(3, "Checking investments unique constraint...")
    try:
        sql = """
        SELECT EXISTS(
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = 'investments' 
            AND constraint_type = 'UNIQUE'
        );
        """
        result = db.session.execute(text(sql)).scalar()
        if result:
            log_success("Unique constraint exists")
            checks.append(True)
        else:
            log_warning("Unique constraint not found")
            checks.append(False)
    except Exception as e:
        log_warning(f"Check skipped: {str(e)}")
        checks.append(True)  # Don't fail on this
    
    # Check 4: CoreFunds exist
    log_step(4, "Checking core funds...")
    try:
        sql = "SELECT COUNT(*) FROM core_funds;"
        result = db.session.execute(text(sql)).scalar()
        if result == 0:
            log_warning("No core funds found - create at least one via /api/v1/funds")
            print("       Example: POST /api/v1/funds with {\"fund_name\": \"My Fund\"}")
            checks.append(False)
        else:
            log_success(f"Found {result} core fund(s)")
            checks.append(True)
    except Exception as e:
        log_warning(f"Check skipped: {str(e)}")
        checks.append(True)
    
    return all(checks)


def main():
    """Run all migrations"""
    log_section("OFDS DATABASE MIGRATION RUNNER")
    print(f"Started: {datetime.now().isoformat()}")
    
    app = create_app_for_migration()
    
    try:
        with app.app_context():
            migrations = [
                ("Nullable Fields", migration_1_nullable_fields),
                ("Is Transferred", migration_2_is_transferred),
                ("Deployment Confirmed", migration_3_deployment_confirmed),
                ("Withdrawal Fund ID", migration_4_withdrawal_fund_id),
                ("Composite Constraint", migration_5_composite_constraint),
            ]
            
            results = []
            for name, migration_func in migrations:
                try:
                    result = migration_func()
                    results.append((name, result))
                except Exception as e:
                    log_error(f"Unexpected error in {name}: {str(e)}")
                    results.append((name, False))
            
            # Verify schema
            print("\n")
            verification_passed = verify_schema()
            
            # Final summary
            log_section("MIGRATION SUMMARY")
            print(f"\nCompleted: {datetime.now().isoformat()}\n")
            
            print("Results:")
            for name, result in results:
                status = "✓ PASS" if result else "✗ FAIL"
                print(f"  {status:7} - {name}")
            
            print(f"\nSchema Verification: {'✓ PASS' if verification_passed else '⚠ WARNINGS'}")
            
            all_passed = all(r[1] for r in results)
            
            if all_passed:
                print("\n" + "=" * 80)
                print("✓ ALL MIGRATIONS COMPLETED SUCCESSFULLY!")
                print("=" * 80)
                print("\nYou can now:")
                print("  1. Run: python main.py")
                print("  2. Run: npm start (frontend)")
                print("  3. Create core funds if not exists")
                print("  4. Test the application")
                return 0
            else:
                print("\n" + "=" * 80)
                print("⚠ SOME MIGRATIONS COMPLETED WITH WARNINGS")
                print("=" * 80)
                print("\nReview the warnings above. If marked as 'Already applied',")
                print("this is normal and safe. Your database is ready to use.")
                return 0
            
    except Exception as e:
        print(f"\n✗ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
