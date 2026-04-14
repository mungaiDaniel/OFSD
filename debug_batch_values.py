"""
Debug script to examine exact batch 1 and batch 2 values in the database.
Shows investments, ledger rows, and calculations for each batch.
"""

import sys
from datetime import datetime
sys.path.insert(0, '/c/Users/Dantez/Downloads/ofds/backend')

from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES
from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)

with app.app_context():
    print("=" * 80)
    print("BATCH 1 ANALYSIS")
    print("=" * 80)
    
    batch1 = db.session.query(Batch).filter(Batch.id == 1).first()
    if batch1:
        print(f"\nBatch Details:")
        print(f"  ID: {batch1.id}")
        print(f"  Name: {batch1.batch_name}")
        print(f"  Date Deployed: {batch1.date_deployed}")
        print(f"  Date Closed: {batch1.date_closed}")
        print(f"  Is Active: {batch1.is_active}")
        
        investments_b1 = db.session.query(Investment).filter(Investment.batch_id == 1).all()
        print(f"\nInvestments in Batch 1: {len(investments_b1)}")
        
        total_principal_b1 = 0.0
        total_current_b1 = 0.0
        
        for inv in investments_b1:
            print(f"\n  Investor: {inv.investor_name} ({inv.internal_client_code})")
            print(f"    Amount Deposited: ${float(inv.amount_deposited):.2f}")
            print(f"    Date Deposited: {inv.date_deposited}")
            print(f"    Fund: {inv.fund.fund_name if inv.fund else inv.fund_name}")
            
            fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
            
            # Get active start date
            active_start = inv.date_transferred or inv.date_deposited or batch1.date_deployed
            print(f"    Active Start: {active_start}")
            
            # Query ledger rows for this investor/fund
            ledger_rows = db.session.query(EpochLedger).filter(
                EpochLedger.internal_client_code == inv.internal_client_code,
                EpochLedger.fund_name == fund_name
            ).all()
            
            print(f"    Total Ledger Rows (all): {len(ledger_rows)}")
            if ledger_rows:
                for i, ledger in enumerate(ledger_rows):
                    print(f"      [{i+1}] {ledger.epoch_start.date()} → {ledger.epoch_end.date()}")
                    print(f"          Start Balance: ${float(ledger.start_balance):.2f}")
                    print(f"          Deposits: ${float(ledger.deposits):.2f}")
                    print(f"          Withdrawals: ${float(ledger.withdrawals):.2f}")
                    print(f"          Profit: ${float(ledger.profit):.2f}")
                    print(f"          End Balance: ${float(ledger.end_balance):.2f}")
            
            # Get withdrawals
            wds = db.session.query(Withdrawal).filter(
                Withdrawal.internal_client_code == inv.internal_client_code,
                Withdrawal.fund_id == inv.fund_id if inv.fund_id else Withdrawal.fund_name == fund_name,
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
            ).all()
            
            total_wds = sum(float(w.amount) for w in wds)
            print(f"    Total Withdrawals: ${total_wds:.2f} ({len(wds)} records)")
            
            # Calculate current balance (matching backend logic)
            opening_balance = float(inv.amount_deposited)
            local_profit = 0.0
            simulated_balance = float(opening_balance)
            
            for ledger in ledger_rows:
                total_capital = float(ledger.start_balance + ledger.deposits)
                ratio = simulated_balance / total_capital if total_capital > 0 else 1.0
                epoch_local_profit = float(ledger.profit) * ratio
                local_profit += epoch_local_profit
                simulated_balance += epoch_local_profit
            
            current_balance = opening_balance + local_profit - total_wds
            
            print(f"    Opening Balance: ${opening_balance:.2f}")
            print(f"    Local Profit: ${local_profit:.2f}")
            print(f"    Calculated Current Balance: ${current_balance:.2f}")
            
            total_principal_b1 += opening_balance
            total_current_b1 += current_balance
        
        print(f"\n  BATCH 1 TOTALS:")
        print(f"    Total Principal: ${total_principal_b1:.2f}")
        print(f"    Total Current Standing: ${total_current_b1:.2f}")
    
    print("\n" + "=" * 80)
    print("BATCH 2 ANALYSIS")
    print("=" * 80)
    
    batch2 = db.session.query(Batch).filter(Batch.id == 2).first()
    if batch2:
        print(f"\nBatch Details:")
        print(f"  ID: {batch2.id}")
        print(f"  Name: {batch2.batch_name}")
        print(f"  Date Deployed: {batch2.date_deployed}")
        print(f"  Date Closed: {batch2.date_closed}")
        print(f"  Is Active: {batch2.is_active}")
        
        investments_b2 = db.session.query(Investment).filter(Investment.batch_id == 2).all()
        print(f"\nInvestments in Batch 2: {len(investments_b2)}")
        
        total_principal_b2 = 0.0
        total_current_b2 = 0.0
        
        for inv in investments_b2:
            print(f"\n  Investor: {inv.investor_name} ({inv.internal_client_code})")
            print(f"    Amount Deposited: ${float(inv.amount_deposited):.2f}")
            print(f"    Date Deposited: {inv.date_deposited}")
            print(f"    Fund: {inv.fund.fund_name if inv.fund else inv.fund_name}")
            
            fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
            
            # Get active start date
            active_start = inv.date_transferred or inv.date_deposited or batch2.date_deployed
            print(f"    Active Start: {active_start}")
            
            # Query ledger rows for this investor/fund
            ledger_rows = db.session.query(EpochLedger).filter(
                EpochLedger.internal_client_code == inv.internal_client_code,
                EpochLedger.fund_name == fund_name
            ).all()
            
            print(f"    Total Ledger Rows (all): {len(ledger_rows)}")
            if ledger_rows:
                for i, ledger in enumerate(ledger_rows):
                    print(f"      [{i+1}] {ledger.epoch_start.date()} → {ledger.epoch_end.date()}")
                    print(f"          Start Balance: ${float(ledger.start_balance):.2f}")
                    print(f"          Deposits: ${float(ledger.deposits):.2f}")
                    print(f"          Withdrawals: ${float(ledger.withdrawals):.2f}")
                    print(f"          Profit: ${float(ledger.profit):.2f}")
                    print(f"          End Balance: ${float(ledger.end_balance):.2f}")
            
            # Get withdrawals
            wds = db.session.query(Withdrawal).filter(
                Withdrawal.internal_client_code == inv.internal_client_code,
                Withdrawal.fund_id == inv.fund_id if inv.fund_id else Withdrawal.fund_name == fund_name,
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
            ).all()
            
            total_wds = sum(float(w.amount) for w in wds)
            print(f"    Total Withdrawals: ${total_wds:.2f} ({len(wds)} records)")
            
            # Calculate current balance (matching backend logic)
            opening_balance = float(inv.amount_deposited)
            local_profit = 0.0
            simulated_balance = float(opening_balance)
            
            for ledger in ledger_rows:
                total_capital = float(ledger.start_balance + ledger.deposits)
                ratio = simulated_balance / total_capital if total_capital > 0 else 1.0
                epoch_local_profit = float(ledger.profit) * ratio
                local_profit += epoch_local_profit
                simulated_balance += epoch_local_profit
            
            current_balance = opening_balance + local_profit - total_wds
            
            print(f"    Opening Balance: ${opening_balance:.2f}")
            print(f"    Local Profit: ${local_profit:.2f}")
            print(f"    Calculated Current Balance: ${current_balance:.2f}")
            
            total_principal_b2 += opening_balance
            total_current_b2 += current_balance
        
        print(f"\n  BATCH 2 TOTALS:")
        print(f"    Total Principal: ${total_principal_b2:.2f}")
        print(f"    Total Current Standing: ${total_current_b2:.2f}")
    
    print("\n" + "=" * 80)
    print(f"GRAND TOTAL (Both Batches):")
    print(f"  Total Principal: ${total_principal_b1 + total_principal_b2:.2f}")
    print(f"  Total Current Standing: ${total_current_b1 + total_current_b2:.2f}")
    print("=" * 80)
