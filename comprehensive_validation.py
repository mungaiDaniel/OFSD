#!/usr/bin/env python3
"""
Comprehensive Atomic Batch Architecture Validation
Identify why Q1-2026 and Q1-2028 show identical values
Run from: backend directory
"""

import sys  
import os

# Add current directory to path so we can import app
sys.path.insert(0, os.path.dirname(__file__))

def comprehensive_validation():
    try:
        from app import create_app
        from app.database.database import db
        from app.Batch.model import Batch
        from app.Batch.controllers import BatchController
        from app.Investments.model import Investment, EpochLedger
        from decimal import Decimal
        
        app = create_app()
        with app.app_context():
            session = db.session
            
            expected = {
                "Portfolio 3": 185877.00,
                "Q1-2026 Portfolio": 282972.43,
                "Q1-2028 Portfolio": 263057.17,
            }
            
            print("\n" + "=" * 140)
            print("COMPREHENSIVE ATOMIC BATCH VALIDATION")
            print("=" * 140)
            
            batches = session.query(Batch).all()
            
            # First, show batch structure
            print("\n1. BATCH STRUCTURE:")
            print("-" * 140)
            for batch in batches:
                inv_count = session.query(Investment).filter(Investment.batch_id == batch.id).count()
                print(f"  ID: {batch.id:<3} | Name: {batch.batch_name:<25} | Date: {batch.date_deployed} | Investments: {inv_count}")
            
            # Now validate each batch calculation
            print("\n2. ATOMIC BATCH TOTALS:")
            print("-" * 140)
            
            for batch_name, expected_total in expected.items():
                batch = session.query(Batch).filter(Batch.batch_name == batch_name).first()
                if not batch:
                    print(f"\n✗ {batch_name} NOT FOUND!")
                    continue
                
                print(f"\n{batch_name}:")
                
                investments = session.query(Investment).filter(
                    Investment.batch_id == batch.id
                ).all()
                
                atomic_sum = Decimal("0")
                
                # Get each investment's ledger value
                for inv in investments:
                    fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
                    latest_ledger = session.query(EpochLedger).filter(
                        EpochLedger.internal_client_code == inv.internal_client_code,
                        EpochLedger.fund_name.ilike(fund_name)
                    ).order_by(EpochLedger.epoch_end.desc()).first()
                    
                    if latest_ledger and latest_ledger.end_balance:
                        atomic_sum += Decimal(str(latest_ledger.end_balance))
                
                calc_total = BatchController._calculate_batch_current_standing(batch, session)
                
                print(f"  Investments: {len(investments)}")
                print(f"  Method calculated: ${calc_total:,.2f}")
                print(f"  Atomic sum: ${float(atomic_sum):,.2f}")
                print(f"  Expected: ${expected_total:,.2f}")
                print(f"  Difference: ${abs(calc_total - expected_total):,.2f}")
                
                if abs(calc_total - expected_total) < 1.00:
                    print(f"  ✅ CORRECT")
                else:
                    print(f"  ❌ WRONG - Need investigation")
            
            # Check for duplicate ledger entries
            print("\n3. LEDGER ENTRY DUPLICATE CHECK:")
            print("-" * 140)
            
            all_investments = session.query(Investment).all()
            duplicate_count = 0
            
            for inv in all_investments:
                fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
                ledger_count = session.query(EpochLedger).filter(
                    EpochLedger.internal_client_code == inv.internal_client_code,
                    EpochLedger.fund_name.ilike(fund_name)
                ).count()
                
                if ledger_count > 1:
                    print(f"⚠️  {inv.investor_name} ({inv.internal_client_code}) has {ledger_count} ledger entries for {fund_name}")
                    duplicate_count += 1
            
            if duplicate_count == 0:
                print("  ✅ No duplicate ledger entries found")
            else:
                print(f"  ⚠️  Found {duplicate_count} investors with multiple ledger entries")
            
            print("\n" + "=" * 140 + "\n")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    comprehensive_validation()
