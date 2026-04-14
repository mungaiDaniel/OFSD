#!/usr/bin/env python
"""
Batch Data Integrity Verification Script
Checks that:
1. Every investment is assigned to a batch
2. batch.total_principal matches the actual sum of investments
3. No investments are missing batch_id
4. Reports batches with mismatched principals
"""

import sys
from config import DevelopmentConfig
from main import create_app
from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment
from sqlalchemy import func

app = create_app(DevelopmentConfig)

def check_batch_integrity():
    """Verify batch data consistency"""
    with app.app_context():
        print("\n" + "="*80)
        print("BATCH DATA INTEGRITY CHECK")
        print("="*80 + "\n")
        
        # Check 1: Investments without batch_id
        orphaned = db.session.query(Investment).filter(
            Investment.batch_id == None
        ).all()
        
        if orphaned:
            print(f"⚠️  WARNING: {len(orphaned)} investments are missing batch_id!")
            for inv in orphaned[:10]:
                print(f"   - Investment ID {inv.id}: {inv.investor_name}")
            print()
        else:
            print("✅ All investments have batch_id assigned")
            print()
        
        # Check 2: Verify each batch's total_principal
        print("%-15s %-30s %-20s %-20s %-10s" % 
              ("Batch ID", "Batch Name", "Stored Total", "Actual Total", "Status"))
        print("-" * 95)
        
        batches = db.session.query(Batch).order_by(Batch.id).all()
        mismatches = []
        
        for batch in batches:
            # Calculate actual sum for this batch
            actual_total = db.session.query(func.sum(Investment.amount_deposited)).filter(
                Investment.batch_id == batch.id
            ).scalar() or 0.0
            
            stored_total = float(batch.total_principal) if batch.total_principal else 0.0
            
            # Count investments in batch
            investment_count = db.session.query(Investment).filter(
                Investment.batch_id == batch.id
            ).count()
            
            # Check if they match
            match_status = "✅ MATCH" if abs(stored_total - actual_total) < 0.01 else "❌ MISMATCH"
            
            if abs(stored_total - actual_total) >= 0.01:
                mismatches.append({
                    'batch_id': batch.id,
                    'batch_name': batch.batch_name,
                    'stored': stored_total,
                    'actual': actual_total,
                    'investment_count': investment_count
                })
            
            print(f"{batch.id:<15} {batch.batch_name:<30} ${stored_total:<19.2f} ${actual_total:<19.2f} {match_status}")
        
        print()
        
        if mismatches:
            print(f"\n⚠️  FOUND {len(mismatches)} MISMATCHES - These need to be fixed:\n")
            for m in mismatches:
                print(f"Batch {m['batch_id']} ({m['batch_name']}):")
                print(f"  - Stored: ${m['stored']:.2f}")
                print(f"  - Actual: ${m['actual']:.2f} ({m['investment_count']} investments)")
                print(f"  - Difference: ${abs(m['stored'] - m['actual']):.2f}")
                print()
            
            # Auto-fix option
            print("\n" + "="*80)
            print("AUTO-FIX: RECALCULATING ALL BATCH TOTALS")
            print("="*80 + "\n")
            
            for batch in batches:
                actual_total = db.session.query(func.sum(Investment.amount_deposited)).filter(
                    Investment.batch_id == batch.id
                ).scalar() or 0.0
                batch.total_principal = actual_total
                print(f"✅ Batch {batch.id} ({batch.batch_name}): Updated total_principal to ${actual_total:.2f}")
            
            db.session.commit()
            print("\n✅ All batch totals have been recalculated and saved!")
        else:
            print("✅ All batch totals are consistent!")
        
        print("\n" + "="*80 + "\n")

if __name__ == '__main__':
    check_batch_integrity()
