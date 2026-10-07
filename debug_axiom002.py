"""
Quick diagnostic script to verify withdrawal calculations for AXIOM-002
"""
import sys
import os
sys.path.insert(0, '/mnt/c/Users/Dantez/Downloads/ofds/backend')

from app import create_app, db
from app.Investments.models import Investment, Withdrawal
from app.Valuation.models import EpochLedger, Statement
from decimal import Decimal

app = create_app()
with app.app_context():
    client_code = "AXIOM-002"
    
    # Get all investments for this client
    investments = db.session.query(Investment).filter(
        Investment.internal_client_code == client_code
    ).all()
    
    print(f"\n{'='*70}")
    print(f"AXIOM-002 WITHDRAWAL CALCULATION AUDIT")
    print(f"{'='*70}\n")
    
    print("1. INVESTMENTS:")
    total_principal = Decimal("0")
    for inv in investments:
        print(f"   - ID {inv.id}: {inv.fund_name}, Amount: ${float(inv.amount_deposited):,.2f}, Deposited: {inv.date_deposited}")
        total_principal += inv.amount_deposited
    print(f"   TOTAL PRINCIPAL: ${float(total_principal):,.2f}\n")
    
    # Get latest epoch ledger
    print("2. EPOCH LEDGER (Latest):")
    ledger = db.session.query(EpochLedger).filter(
        EpochLedger.internal_client_code == client_code
    ).order_by(EpochLedger.epoch_end.desc()).first()
    
    if ledger:
        print(f"   Epoch: {ledger.epoch_start} to {ledger.epoch_end}")
        print(f"   Fund: {ledger.fund_name}")
        print(f"   Start Balance: ${float(ledger.start_balance):,.2f}")
        print(f"   Deposits: ${float(ledger.deposits):,.2f}")
        print(f"   Withdrawals (in epoch): ${float(ledger.withdrawals):,.2f}")
        print(f"   Profit: ${float(ledger.profit):,.2f}")
        print(f"   End Balance: ${float(ledger.end_balance):,.2f}\n")
    else:
        print("   No epoch ledger found\n")
    
    # Get all withdrawals
    print("3. WITHDRAWALS:")
    withdrawals = db.session.query(Withdrawal).filter(
        Withdrawal.internal_client_code == client_code
    ).all()
    
    if withdrawals:
        for w in withdrawals:
            print(f"   - ID {w.id}: ${float(w.amount):,.2f}")
            print(f"     Status: {w.status}")
            print(f"     Fund: {w.fund_name}")
            print(f"     Created: {w.created_at}")
            print(f"     Approved: {w.approved_at}")
            print(f"     Paid: {w.paid_at if hasattr(w, 'paid_at') else 'N/A'}")
        
        total_withdrawals = sum(w.amount for w in [w for w in withdrawals if w.status in ['APPROVED', 'PAID']])
        print(f"   TOTAL APPROVED/PAID: ${float(total_withdrawals):,.2f}\n")
    else:
        print("   No withdrawals found\n")
    
    # Calculate what it should be
    print("4. CALCULATION CHECK:")
    if ledger:
        current_standing_should_be = Decimal(str(ledger.end_balance))
        if withdrawals:
            approved_wd = sum(Decimal(str(w.amount)) for w in withdrawals if w.status in ['APPROVED', 'PAID'] and (not hasattr(w, 'approved_at') or w.approved_at is None or w.approved_at > ledger.epoch_end))
            current_standing_should_be -= approved_wd
            print(f"   Post-epoch approved withdrawals: ${float(approved_wd):,.2f}")
        
        print(f"   End Balance from Epoch: ${float(ledger.end_balance):,.2f}")
        print(f"   SHOULD DISPLAY AS: ${float(current_standing_should_be):,.2f}")
        print(f"   BUT DISPLAYING AS: ${float(ledger.end_balance):,.2f} ← BUG!")
        
        if current_standing_should_be != ledger.end_balance:
            diff = ledger.end_balance - current_standing_should_be
            print(f"   DIFFERENCE: ${float(diff):,.2f} (amount being hidden)\n")
    
    print("5. FRONTEND FORMULA NEEDED:")
    print(f"   current_standing = end_balance - (legacy_withdrawals_after_epoch)")
