#!/usr/bin/env python3
"""
Quick validation that batch totals now match expected values using ledger approach.
"""

import sys  
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def validate_batch_fix():
    try:
        from app import create_app
        from app.database.database import db
        from app.Batch.controllers import BatchController
        from app.Batch.model import Batch
        from app.Investments.model import Investment
        
        app = create_app()
        with app.app_context():
            session = db.session
            
            expected = {
                "Portfolio 3": 185877.00,
                "Q1-2026 Portfolio": 282972.43,
                "Q1-2028 Portfolio": 263057.17,
            }
            
            batches = session.query(Batch).all()
            
            print("\n" + "=" * 80)
            print("BATCH TOTALS VALIDATION - LEDGER-BASED CALCULATION")
            print("=" * 80)
            
            all_correct = True
            grand_total = 0.0
            
            for batch in batches:
                # Get all investments in batch
                investments = session.query(Investment).filter(
                    Investment.batch_id == batch.id
                ).all()
                
                # Calculate using the new method
                total = BatchController._calculate_batch_current_standing(batch, session)
                grand_total += total
                
                expected_val = expected.get(batch.batch_name)
                
                print(f"\n{batch.batch_name}:")
                print(f"  Investments: {len(investments)}")
                print(f"  Calculated:  ${total:>12,.2f}")
                
                if expected_val:
                    diff = abs(total - expected_val)
                    match = diff < 1.00
                    print(f"  Expected:    ${expected_val:>12,.2f}")
                    print(f"  Difference:  ${diff:>12,.2f}")
                    print(f"  Result:      {'✅ CORRECT' if match else '❌ WRONG'}")
                    if not match:
                        all_correct = False
            
            print(f"\n{'-' * 80}")
            print(f"Grand Total:          ${grand_total:>12,.2f}")
            print(f"Expected Grand Total: ${sum(expected.values()):>12,.2f}")
            print(f"Difference:           ${abs(grand_total - sum(expected.values())):>12,.2f}")
            
            print("\n" + ("✅ ALL BATCHES CORRECT!" if all_correct else "❌ FIX STILL INCOMPLETE"))
            print("=" * 80 + "\n")
            
            return all_correct
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = validate_batch_fix()
    sys.exit(0 if success else 1)
