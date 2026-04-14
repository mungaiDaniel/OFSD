"""Debug script to examine batch 1 and batch 2 values."""

import sys
sys.path.insert(0, 'c:\\Users\\Dantez\\Downloads\\ofds\\backend')

from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES
from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)

with app.app_context():
    print("\n" + "="*80)
    print("BATCH 1 & 2 VALUE ANALYSIS")
    print("="*80 + "\n")
    
    for batch_id in [1, 2]:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            print(f"Batch {batch_id} not found")
            continue
        
        print(f"BATCH {batch_id}: {batch.batch_name}")
        print(f"  Date Deployed: {batch.date_deployed}")
        print(f"  Is Active: {batch.is_active}\n")
        
        investments = db.session.query(Investment).filter(Investment.batch_id == batch_id).all()
        total_principal = 0.0
        total_current = 0.0
        
        for inv in investments:
            principal = float(inv.amount_deposited)
            total_principal += principal
            
            # Check if batch is deployed
            if batch.date_deployed is None:
                # Undeployed: show only principal
                current = principal
                print(f"    {inv.investor_name} ({inv.internal_client_code}): ${principal:.2f} (no ledger - undeployed)")
            else:
                # Deployed: calculate with ledger
                fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
                active_start = inv.date_transferred or inv.date_deposited or batch.date_deployed
                active_start_naive = active_start.replace(tzinfo=None) if active_start and getattr(active_start, 'tzinfo', None) else active_start
                
                batch_deploy_naive = batch.date_deployed.replace(tzinfo=None) if getattr(batch.date_deployed, 'tzinfo', None) else batch.date_deployed
                if active_start_naive is None or active_start_naive < batch_deploy_naive:
                    active_start_naive = batch_deploy_naive
                
                ledgers = db.session.query(EpochLedger).filter(
                    EpochLedger.internal_client_code == inv.internal_client_code,
                    EpochLedger.fund_name == fund_name,
                    EpochLedger.epoch_end > active_start_naive
                ).all()
                
                local_profit = 0.0
                sim_bal = principal
                for l in ledgers:
                    total_cap = float(l.start_balance + l.deposits)
                    ratio = sim_bal / total_cap if total_cap > 0 else 1.0
                    epoch_profit = float(l.profit) * ratio
                    local_profit += epoch_profit
                    sim_bal += epoch_profit
                
                wds = db.session.query(Withdrawal).filter(
                    Withdrawal.internal_client_code == inv.internal_client_code,
                    Withdrawal.fund_id == inv.fund_id if inv.fund_id else Withdrawal.fund_name == fund_name,
                    Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                    Withdrawal.date_withdrawn >= active_start_naive
                ).all()
                
                total_wds = sum(float(w.amount) for w in wds)
                current = principal + local_profit - total_wds
                
                print(f"    {inv.investor_name} ({inv.internal_client_code}): ${current:.2f} (principal ${principal:.2f} + profit ${local_profit:.2f} - wd ${total_wds:.2f})")
            
            total_current += current
        
        print(f"\n  BATCH {batch_id} TOTALS:")
        print(f"    Principal: ${total_principal:,.2f}")
        print(f"    Current Standing: ${total_current:,.2f}\n")
    
    print("="*80)
    batch1_val = 271972.68  # from previous debug
    batch2_val = 250000.00  # expected
    print(f"Expected Batch 1: ${batch1_val:,.2f}")
    print(f"Expected Batch 2: ${batch2_val:,.2f}")
    print(f"Expected Total: ${batch1_val + batch2_val:,.2f}")
    print("="*80 + "\n")
