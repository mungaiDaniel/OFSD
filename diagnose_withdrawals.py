#!/usr/bin/env python3
"""Diagnostic script to check withdrawal data"""
import sys
sys.path.insert(0, '/app' if __name__ == '__main__' else '.')

from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment, Withdrawal, FINAL_WITHDRAWAL_STATUSES
from app.Batch.model import Batch

app = create_app(Config)
with app.app_context():
    print("\n" + "="*70)
    print("WITHDRAWAL DATA DIAGNOSTIC")
    print("="*70)
    
    # Get batches 1, 2, 3
    for batch_id in [1, 2, 3]:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            print(f"\n❌ Batch {batch_id} not found\n")
            continue
            
        print(f"\n📦 BATCH {batch_id}: {batch.batch_name}")
        print("-" * 70)
        
        # Get all investments in this batch
        investments = db.session.query(Investment).filter(Investment.batch_id == batch_id).all()
        print(f"📊 Investments: {len(investments)}")
        
        total_withdrawals = 0
        
        for inv in investments:
            print(f"\n  👤 {inv.internal_client_code} ({inv.investor_name})")
            print(f"     Amount deposited: ${float(inv.amount_deposited):,.2f}")
            print(f"     Fund: {inv.fund.fund_name if inv.fund else inv.fund_name}")
            
            # Query withdrawals for this investor
            fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
            withdrawals = db.session.query(Withdrawal).filter(
                Withdrawal.internal_client_code == inv.internal_client_code,
                Withdrawal.fund_name == fund_name
            ).all()
            
            print(f"     Total withdrawal records: {len(withdrawals)}")
            
            # Show status breakdown
            status_count = {}
            for wd in withdrawals:
                status = wd.status or "Unknown"
                status_count[status] = status_count.get(status, 0) + 1
                print(f"       - Status: {status}, Amount: ${float(wd.amount):,.2f}")
            
            # Calculate final withdrawals (only those in FINAL_WITHDRAWAL_STATUSES)
            final_wds = db.session.query(Withdrawal).filter(
                Withdrawal.internal_client_code == inv.internal_client_code,
                Withdrawal.fund_name == fund_name,
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
            ).all()
            
            final_total = sum(float(wd.amount) for wd in final_wds)
            print(f"     ✓ Final withdrawal statuses ({final_wds.__len__()} records): ${final_total:,.2f}")
            total_withdrawals += final_total
        
        print(f"\n   📈 TOTAL WITHDRAWALS FOR BATCH {batch_id}: ${total_withdrawals:,.2f}")
    
    # Check total across all 3 batches
    print(f"\n" + "="*70)
    print("SUMMARY ACROSS ALL BATCHES")
    print("="*70)
    
    all_wds = db.session.query(Withdrawal).filter(
        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
    ).all()
    
    grand_total = sum(float(wd.amount) for wd in all_wds)
    print(f"Total withdrawal records with FINAL status: {len(all_wds)}")
    print(f"Grand total withdrawals: ${grand_total:,.2f}")
    
    print(f"\nFINAL_WITHDRAWAL_STATUSES: {FINAL_WITHDRAWAL_STATUSES}")
    print("\n" + "="*70 + "\n")
