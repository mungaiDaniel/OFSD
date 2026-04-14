#!/usr/bin/env python
"""
Batch Isolation & Data Leakage Diagnostic
Checks for cross-batch data pollution and row count accuracy
"""

import sys
from config import DevelopmentConfig
from main import create_app
from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment
from sqlalchemy import func

app = create_app(DevelopmentConfig)

def diagnose_batch_isolation():
    """Comprehensive batch isolation diagnostic"""
    with app.app_context():
        print("\n" + "="*100)
        print("BATCH ISOLATION DIAGNOSTIC")
        print("="*100 + "\n")
        
        # Global stats
        total_investments = db.session.query(Investment).count()
        total_sum = db.session.query(func.sum(Investment.amount_deposited)).scalar() or 0.0
        
        print(f"GLOBAL STATISTICS:")
        print(f"  Total Investment Rows: {total_investments}")
        print(f"  Global Sum: ${total_sum:.2f}")
        print()
        
        # Per-batch analysis
        batches = db.session.query(Batch).order_by(Batch.id).all()
        
        print(f"PER-BATCH BREAKDOWN (Expected: Each batch shows ONLY its own data):")
        print("-" * 100)
        print(f"{'Batch ID':<10} {'Batch Name':<30} {'Stored Total':<20} {'Calculated':<20} {'Row Count':<12} {'Status':<15}")
        print("-" * 100)
        
        total_check = 0
        issues = []
        
        for batch in batches:
            # Calculate batch-specific total
            batch_calculated = db.session.query(func.sum(Investment.amount_deposited)).filter(
                Investment.batch_id == batch.id
            ).scalar() or 0.0
            
            # Count rows for this batch
            row_count = db.session.query(Investment).filter(
                Investment.batch_id == batch.id
            ).count()
            
            # Get stored value
            stored_total = float(batch.total_principal) if batch.total_principal else 0.0
            
            # Check for match
            mismatch = abs(stored_total - batch_calculated) > 0.01
            status = "❌ MISMATCH" if mismatch else "✅ OK"
            
            if mismatch:
                issues.append({
                    'batch_id': batch.id,
                    'stored': stored_total,
                    'calculated': batch_calculated,
                    'rows': row_count
                })
            
            print(f"{batch.id:<10} {batch.batch_name:<30} ${stored_total:<19.2f} ${batch_calculated:<19.2f} {row_count:<12} {status:<15}")
            total_check += batch_calculated
        
        print("-" * 100)
        print(f"{'TOTAL':<10} {'(should equal global sum above)':<30} {'  ':<20} ${total_check:<19.2f}")
        print()
        
        # Cross-batch contamination check
        print(f"CROSS-BATCH CONTAMINATION CHECK:")
        print("-" * 100)
        
        for batch in batches:
            batch_investments = db.session.query(Investment).filter(
                Investment.batch_id == batch.id
            ).all()
            
            # Check if any show up in global queries unfiltered (they shouldn't)
            for inv in batch_investments:
                fund_code = inv.internal_client_code
                
                # Count how many times this code appears ACROSS ALL BATCHES
                all_batch_count = db.session.query(Investment).filter(
                    Investment.internal_client_code == fund_code
                ).count()
                
                batch_count = db.session.query(Investment).filter(
                    Investment.batch_id == batch.id,
                    Investment.internal_client_code == fund_code
                ).count()
                
                if all_batch_count > batch_count:
                    print(f"⚠️  Code '{fund_code}' appears in multiple batches (Batch {batch.id}: {batch_count} rows, Total: {all_batch_count} rows)")
                    break
            else:
                print(f"✅ Batch {batch.id}: No cross-batch contamination detected")
        
        print()
        
        if issues:
            print(f"\n⚠️  FOUND {len(issues)} ISSUES:\n")
            for issue in issues:
                print(f"Batch {issue['batch_id']}:")
                print(f"  Rows: {issue['rows']}")
                print(f"  Stored: ${issue['stored']:.2f}")
                print(f"  Calculated: ${issue['calculated']:.2f}")
                print(f"  Difference: ${abs(issue['stored'] - issue['calculated']):.2f}")
                print()
        else:
            print("✅ All batches are properly isolated!")
        
        print("="*100 + "\n")

if __name__ == '__main__':
    diagnose_batch_isolation()
