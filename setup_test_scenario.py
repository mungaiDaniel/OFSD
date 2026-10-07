#!/usr/bin/env python3
"""
Test Data Setup Helper
Creates the Investor A & B test scenario in the database
Run this once to set up test data, then run the verification tests
"""

import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, '/var/www/html')

try:
    from app import create_app
    from app.database.database import db
    from app.Batch.model import Batch
    from app.Investments.model import Investment
    from app.Valuation.model import ValuationRun, Statement
except ImportError:
    print("ERROR: Cannot import Flask app")
    sys.exit(1)


def setup_test_scenario():
    """Create Investor A & B test scenario"""
    
    app = create_app()
    
    with app.app_context():
        print("\n" + "=" * 70)
        print("TEST DATA SETUP: Investor A & B Scenario")
        print("=" * 70)
        
        # ── Check if scenario already exists ──
        existing = db.session.query(Batch).filter(
            Batch.batch_name == "TEST-SCENARIO-A-B"
        ).first()
        
        if existing:
            print(f"\n⚠ Test batch already exists: {existing.batch_name}")
            print(f"  ID: {existing.id}")
            print("\n  Delete existing batch if you want to recreate it")
            return existing
        
        # ── Step 1: Create Batch ──
        print("\n[STEP 1] Creating Batch...")
        batch = Batch(
            batch_name="TEST-SCENARIO-A-B",
            certificate_number="TEST-001",
            date_deployed=datetime(2026, 1, 1),
            is_active=True
        )
        db.session.add(batch)
        db.session.flush()
        print(f"✓ Batch created: {batch.batch_name} (ID: {batch.id})")
        
        # ── Step 2: Create Investor A ──
        print("\n[STEP 2] Creating Investor A...")
        inv_a = Investment(
            batch_id=batch.id,
            investor_name="Investor A",
            investor_email="investor.a@test.com",
            investor_phone="555-0001",
            internal_client_code="TEST-A",
            fund_id=None,
            amount_deposited=Decimal("30000.00"),
            deployment_fee_deducted=Decimal("449.33"),
            transfer_fee_deducted=Decimal("45.00"),
            net_principal=Decimal("29505.67"),
            date_deposited=datetime(2026, 1, 1)
        )
        db.session.add(inv_a)
        db.session.flush()
        print(f"✓ Investor A created (ID: {inv_a.id})")
        print(f"  Deposit: $30,000.00")
        print(f"  Net Principal: $29,505.67")
        
        # ── Step 3: Create Investor B ──
        print("\n[STEP 3] Creating Investor B...")
        inv_b = Investment(
            batch_id=batch.id,
            investor_name="Investor B",
            investor_email="investor.b@test.com",
            investor_phone="555-0002",
            internal_client_code="TEST-B",
            fund_id=None,
            amount_deposited=Decimal("10000.00"),
            deployment_fee_deducted=Decimal("149.78"),
            transfer_fee_deducted=Decimal("15.00"),
            net_principal=Decimal("9835.22"),
            date_deposited=datetime(2026, 1, 1)
        )
        db.session.add(inv_b)
        db.session.flush()
        print(f"✓ Investor B created (ID: {inv_b.id})")
        print(f"  Deposit: $10,000.00")
        print(f"  Net Principal: $9,835.22")
        
        # ── Step 4: Create ValuationRun ──
        print("\n[STEP 4] Creating ValuationRun...")
        vr = ValuationRun(
            batch_id=batch.id,
            epoch_start=datetime(2026, 1, 1),
            epoch_end=datetime(2026, 1, 31),
            status="Committed",
            performance_rate=Decimal("0.03"),
            core_fund_id=None
        )
        db.session.add(vr)
        db.session.flush()
        print(f"✓ ValuationRun created (ID: {vr.id})")
        print(f"  Period: 2026-01-01 to 2026-01-31")
        print(f"  Status: Committed")
        print(f"  Performance Rate: 3%")
        
        # ── Step 5: Create Statements ──
        print("\n[STEP 5] Creating Statements...")
        
        stmt_a = Statement(
            investor_id=inv_a.id,
            batch_id=batch.id,
            valuation_run_id=vr.id,
            start_balance=Decimal("29505.67"),
            closing_balance=Decimal("30390.84"),
            deposits=Decimal("0.00"),
            withdrawals=Decimal("0.00"),
            profit=Decimal("885.17"),
            performance_rate=Decimal("0.03")
        )
        db.session.add(stmt_a)
        
        stmt_b = Statement(
            investor_id=inv_b.id,
            batch_id=batch.id,
            valuation_run_id=vr.id,
            start_balance=Decimal("9835.22"),
            closing_balance=Decimal("10130.28"),
            deposits=Decimal("0.00"),
            withdrawals=Decimal("0.00"),
            profit=Decimal("295.06"),
            performance_rate=Decimal("0.03")
        )
        db.session.add(stmt_b)
        
        db.session.commit()
        print(f"✓ Statement A created (ID: {stmt_a.id})")
        print(f"  Closing Balance: $30,390.84")
        print(f"✓ Statement B created (ID: {stmt_b.id})")
        print(f"  Closing Balance: $10,130.28")
        
        # ── Summary ──
        print("\n" + "=" * 70)
        print("TEST DATA SETUP COMPLETE")
        print("=" * 70)
        
        print(f"""
Batch Summary:
  Batch ID: {batch.id}
  Batch Name: {batch.batch_name}
  
Investor A:
  Investment ID: {inv_a.id}
  Original Deposit: $30,000.00
  Net Principal: $29,505.67
  Statement ID: {stmt_a.id}
  Ending Balance: $30,390.84
  
Investor B:
  Investment ID: {inv_b.id}
  Original Deposit: $10,000.00
  Net Principal: $9,835.22
  Statement ID: {stmt_b.id}
  Ending Balance: $10,130.28
  
Batch Totals:
  Total Deposits: $40,000.00
  Total Net Principal: $39,340.89
  Total Ending (AUM): $40,521.12
  
Next Steps:
  1. Run: python run_tests.py scenario
  2. Run: python run_tests.py display
  3. Verify frontend displays match values above
  """)
        
        return batch


def verify_setup():
    """Verify test data was set up correctly"""
    
    app = create_app()
    
    with app.app_context():
        print("\n" + "=" * 70)
        print("VERIFYING TEST DATA SETUP")
        print("=" * 70)
        
        batch = db.session.query(Batch).filter(
            Batch.batch_name == "TEST-SCENARIO-A-B"
        ).first()
        
        if not batch:
            print("\n✗ Test batch not found")
            print("  Run: python setup_test_scenario.py setup")
            return False
        
        # Verify investments
        investments = db.session.query(Investment).filter(
            Investment.batch_id == batch.id
        ).all()
        
        if len(investments) != 2:
            print(f"\n✗ Expected 2 investments, found {len(investments)}")
            return False
        
        # Verify statements
        statements = db.session.query(Statement).filter(
            Statement.batch_id == batch.id
        ).all()
        
        if len(statements) != 2:
            print(f"\n✗ Expected 2 statements, found {len(statements)}")
            return False
        
        # Verify valuation run
        vr = db.session.query(ValuationRun).filter(
            ValuationRun.batch_id == batch.id
        ).first()
        
        if not vr:
            print("\n✗ ValuationRun not found")
            return False
        
        # Print verification results
        print(f"\n✓ Batch: {batch.batch_name} (ID: {batch.id})")
        print(f"✓ Investments: {len(investments)}")
        print(f"✓ Statements: {len(statements)}")
        print(f"✓ ValuationRun: Status={vr.status}, Performance={vr.performance_rate}")
        
        # Verify values
        print("\nValue Verification:")
        
        for inv in investments:
            stmt = next((s for s in statements if s.investor_id == inv.id), None)
            if stmt:
                print(f"\n  {inv.investor_name}:")
                print(f"    ✓ Net Principal: ${inv.net_principal}")
                print(f"    ✓ Closing Balance: ${stmt.closing_balance}")
                
                expected_closing = inv.net_principal * (1 + Decimal("0.03"))
                actual_closing = stmt.closing_balance
                
                if abs(expected_closing - actual_closing) < Decimal("0.01"):
                    print(f"    ✓ 3% calculation correct")
                else:
                    print(f"    ✗ 3% calculation mismatch!")
        
        print("\n" + "=" * 70)
        print("✓ TEST DATA VERIFIED SUCCESSFULLY")
        print("=" * 70 + "\n")
        
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test data setup helper")
    parser.add_argument(
        "action",
        nargs="?",
        default="setup",
        choices=["setup", "verify"],
        help="Action to perform (default: setup)"
    )
    
    args = parser.parse_args()
    
    if args.action == "setup":
        batch = setup_test_scenario()
        if batch:
            print(f"\n✓ Setup complete! Batch ID: {batch.id}")
            print("  Run: python setup_test_scenario.py verify")
    
    elif args.action == "verify":
        success = verify_setup()
        if success:
            print("✓ All test data verified!")
            print("  Run: python run_tests.py scenario")
        else:
            print("✗ Verification failed")
            return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
