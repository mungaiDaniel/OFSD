#!/usr/bin/env python
"""
Check EpochLedger withdrawal data using raw SQL
"""
import sys
sys.path.insert(0, 'c:\\Users\\Dantez\\Downloads\\ofds\\backend')

from config import DevelopmentConfig as Config
from app.database.database import db
from flask import Flask

# Setup app
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    with db.engine.connect() as conn:
        print("=" * 80)
        print("EPOCH LEDGER WITHDRAWAL ANALYSIS (RAW SQL)")
        print("=" * 80)
        
        # Get a sample investment from Batch 1
        result = conn.execute(db.text("""
            SELECT id, internal_client_code, fund_name 
            FROM investments 
            WHERE batch_id = 1 
            LIMIT 1
        """)).fetchone()
        
        if not result:
            print("No investments in Batch 1")
            sys.exit(1)
        
        inv_id, code, fund = result
        print(f"\nAnalyzing investment: {code}, Fund: {fund}")
        
        # Check Withdrawal table
        wd_result = conn.execute(db.text("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM withdrawals
            WHERE internal_client_code = :code 
              AND fund_name = :fund
              AND status IN ('Approved', 'Processed', 'Completed', 'Executed')
        """), {"code": code, "fund": fund}).fetchone()
        
        total_approved_wds = float(wd_result[0]) if wd_result else 0
        print(f"\n1. Total Approved Withdrawals (Withdrawal table):")
        print(f"   ${total_approved_wds:,.2f}")
        
        # Check EpochLedger
        epoch_result = conn.execute(db.text("""
            SELECT COALESCE(SUM(withdrawals), 0) as total
            FROM epoch_ledger
            WHERE internal_client_code = :code 
              AND fund_name = :fund
        """), {"code": code, "fund": fund}).fetchone()
        
        total_captured_wds = float(epoch_result[0]) if epoch_result else 0
        print(f"\n2. Total Captured Withdrawals (EpochLedger table):")
        print(f"   ${total_captured_wds:,.2f}")
        
        # Calculate uncaptured
        uncaptured = max(0, total_approved_wds - total_captured_wds)
        print(f"\n3. Uncaptured Withdrawals (for proportional allocation):")
        print(f"   ${uncaptured:,.2f}")
        
        # Show sample EpochLedger records
        epochs = conn.execute(db.text("""
            SELECT epoch_end, withdrawals
            FROM epoch_ledger
            WHERE internal_client_code = :code 
              AND fund_name = :fund
            ORDER BY epoch_end DESC
            LIMIT 5
        """), {"code": code, "fund": fund}).fetchall()
        
        print(f"\n4. EpochLedger records for this investor/fund: {len(epochs)}")
        if epochs:
            for epoch_end, withdrawals in epochs:
                print(f"   - Epoch {epoch_end}: withdrawals = ${float(withdrawals):,.2f}")
        else:
            print(f"   *** NO EPOCH LEDGER RECORDS FOUND ***")
        
        print("\n" + "=" * 80)
        print("INTERPRETATION:")
        if uncaptured == 0:
            print("  ⚠️  uncaptured_wds = 0 → withdrawal_share will be 0")
            print("     This means ALL withdrawals are already captured in EpochLedger.")
            print("     The backend will return withdrawals = $0 for this investment.")
        else:
            print(f"  ✓ uncaptured_wds = ${uncaptured:,.2f}")
            print("   Withdrawals will be prorated based on investment's share of holdings.")
        print("=" * 80)
