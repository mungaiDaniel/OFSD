#!/usr/bin/env python3
"""
Detailed diagnostic of investment dates and ledger epochs.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import app
from app.database.database import db
from app.Investments.model import Investment, EpochLedger
from app.Batch.model import Batch
from datetime import datetime

def debug_dates():
    with app.app_context():
        print("\n" + "="*80)
        print("INVESTMENT DATES vs LEDGER EPOCHS")
        print("="*80)
        
        # Get all investments with their details
        investments = db.session.query(Investment).all()
        print(f"\n📋 All Investments ({len(investments)} total):\n")
        
        for inv in sorted(investments, key=lambda x: x.batch_id):
            print(f"Batch {inv.batch_id} | {inv.internal_client_code:12} | {inv.fund_name:8} | Amount: ${float(inv.amount_deposited):>10,.2f} | Deposited: {inv.date_deposited.date() if inv.date_deposited else 'N/A'}")
        
        # Get all ledgers
        ledgers = db.session.query(EpochLedger).order_by(
            EpochLedger.internal_client_code,
            EpochLedger.epoch_end
        ).all()
        
        print(f"\n📊 All Ledger Epochs ({len(ledgers)} total):\n")
        for ledger in ledgers:
            print(f"{ledger.internal_client_code:12} | {ledger.fund_name:8} | Epoch: {ledger.epoch_start.date()} to {ledger.epoch_end.date()} | End Balance: ${float(ledger.end_balance):>10,.2f}")
        
        # Check which investments are after the latest epoch
        latest_epoch = max((l.epoch_end for l in ledgers), default=None)
        if latest_epoch:
            print(f"\n🔍 Latest Epoch Across All Ledgers: {latest_epoch.date()}\n")
            print("Investments deposited AFTER latest epoch:\n")
            
            for inv in investments:
                if inv.date_deposited:
                    inv_date_naive = inv.date_deposited.replace(tzinfo=None) if inv.date_deposited.tzinfo else inv.date_deposited
                    epoch_date_naive = latest_epoch.replace(tzinfo=None) if latest_epoch.tzinfo else latest_epoch
                    
                    if inv_date_naive > epoch_date_naive:
                        print(f"  ✓ Batch {inv.batch_id} | {inv.internal_client_code:12} | Deposited: {inv_date_naive.date()} | Amount: ${float(inv.amount_deposited):>10,.2f}")
            
            all_after = [inv for inv in investments if inv.date_deposited and (inv.date_deposited.replace(tzinfo=None) if inv.date_deposited.tzinfo else inv.date_deposited) > epoch_date_naive]
            if not all_after:
                print(f"  ❌ NO investments found after {latest_epoch.date()}")
                total_after = sum(inv.amount_deposited or 0 for inv in all_after)
                print(f"\n  Total fresh deposit amount: ${float(total_after):,.2f}")

if __name__ == '__main__':
    debug_dates()
