#!/usr/bin/env python3
"""
Verification Script: Check Withdrawal-CoreFund Sync
Date: March 17, 2026

This script verifies that the withdrawals table has been properly
migrated with the fund_id column and relationships.
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
from app.Investments.model import Withdrawal
from app.Batch.core_fund import CoreFund


def verify_migration():
    """Verify the migration was successful"""
    app = create_app()
    
    with app.app_context():
        print("=" * 80)
        print("Verification: Withdrawal-CoreFund Sync")
        print("=" * 80)
        
        # Check 1: Verify column exists
        print("\n[CHECK 1] Verifying fund_id column exists in withdrawals table...")
        try:
            check_sql = """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'withdrawals' AND column_name = 'fund_id'
            );
            """
            result = db.session.execute(db.text(check_sql)).scalar()
            if result:
                print("    ✓ fund_id column EXISTS")
            else:
                print("    ✗ fund_id column MISSING - migration not run yet!")
                return False
        except Exception as e:
            print(f"    ✗ Error checking column: {str(e)}")
            return False
        
        # Check 2: Verify NOT NULL constraint
        print("\n[CHECK 2] Verifying fund_id NOT NULL constraint...")
        try:
            check_sql = """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'withdrawals' AND column_name = 'fund_id';
            """
            result = db.session.execute(db.text(check_sql)).scalar()
            if result == False:  # is_nullable = False means NOT NULL
                print("    ✓ fund_id is NOT NULL")
            elif result == True:
                print("    ⚠ fund_id is NULLABLE (should be NOT NULL)")
            else:
                print(f"    ? Unknown nullable status: {result}")
        except Exception as e:
            print(f"    ✗ Error checking constraint: {str(e)}")
        
        # Check 3: Verify foreign key exists
        print("\n[CHECK 3] Verifying foreign key constraint...")
        try:
            check_sql = """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = 'withdrawals' AND constraint_type = 'FOREIGN KEY'
                AND constraint_name LIKE '%fund%'
            );
            """
            result = db.session.execute(db.text(check_sql)).scalar()
            if result:
                print("    ✓ Foreign key constraint EXISTS")
            else:
                print("    ⚠ Foreign key constraint not found (may not be created yet)")
        except Exception as e:
            print(f"    ⚠ Error checking FK: {str(e)}")
        
        # Check 4: Verify index exists
        print("\n[CHECK 4] Verifying index on (code, fund, date)...")
        try:
            check_sql = """
            SELECT EXISTS(
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'withdrawals' 
                AND indexname = 'ix_withdrawals_code_fund_date'
            );
            """
            result = db.session.execute(db.text(check_sql)).scalar()
            if result:
                print("    ✓ Index ix_withdrawals_code_fund_date EXISTS")
            else:
                print("    ⚠ Index not found")
        except Exception as e:
            print(f"    ⚠ Error checking index: {str(e)}")
        
        # Check 5: Test relationship
        print("\n[CHECK 5] Testing Withdrawal-CoreFund relationship...")
        try:
            # Get first withdrawal
            withdrawal = db.session.query(Withdrawal).first()
            if withdrawal:
                print(f"    Sample withdrawal: ID={withdrawal.id}, code={withdrawal.internal_client_code}")
                print(f"    fund_id value: {withdrawal.fund_id}")
                
                # Try to access the fund relationship
                if withdrawal.fund_id:
                    fund = db.session.query(CoreFund).filter(CoreFund.id == withdrawal.fund_id).first()
                    if fund:
                        print(f"    ✓ Fund relationship works: fund.fund_name = '{fund.fund_name}'")
                    else:
                        print(f"    ✗ Fund not found for fund_id={withdrawal.fund_id}")
                        print("       Ensure CoreFund records exist for all fund_ids")
                else:
                    print("    ⚠ Withdrawal has NULL fund_id")
            else:
                print("    ℹ No withdrawals yet (table may be empty)")
        except Exception as e:
            print(f"    ✗ Error testing relationship: {str(e)}")
            return False
        
        # Check 6: Count withdrawals
        print("\n[CHECK 6] Withdrawal records count...")
        try:
            count = db.session.query(Withdrawal).count()
            print(f"    Total withdrawals: {count}")
            
            # Check for NULL fund_ids
            null_count = db.session.query(Withdrawal).filter(Withdrawal.fund_id == None).count()
            if null_count > 0:
                print(f"    ⚠ {null_count} withdrawals have NULL fund_id (should be none)")
            else:
                print(f"    ✓ All withdrawals have fund_id assigned")
        except Exception as e:
            print(f"    ✗ Error counting: {str(e)}")
        
        # Check 7: Verify CoreFund records
        print("\n[CHECK 7] Verifying CoreFund records...")
        try:
            funds = db.session.query(CoreFund).all()
            if not funds:
                print("    ✗ NO CORE FUNDS FOUND! Create at least one fund first:")
                print("       Example: POST /api/v1/funds with {\"fund_name\": \"My Fund\"}")
            else:
                print(f"    ✓ Found {len(funds)} core fund(s):")
                for fund in funds:
                    print(f"       - ID={fund.id}, Name={fund.fund_name}, Active={fund.is_active}")
        except Exception as e:
            print(f"    ✗ Error checking funds: {str(e)}")
        
        # Summary
        print("\n" + "=" * 80)
        print("✓ Verification Complete!")
        print("=" * 80)
        
        print("\nWhat to do next:")
        print("1. If all checks pass: Run 'python main.py' to start backend")
        print("2. Test withdrawal creation via API or frontend")
        print("3. Verify funds are displayed in WithdrawalManager page")
        
        return True


if __name__ == '__main__':
    try:
        success = verify_migration()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Verification interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Verification failed: {str(e)}")
        sys.exit(1)
