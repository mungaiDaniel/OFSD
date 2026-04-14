#!/usr/bin/env python3
"""
Trace batch calculation step-by-step for debugging
Run from: backend directory
"""

import sys  
import os

# Add current directory to path so we can import app
sys.path.insert(0, os.path.dirname(__file__))

def trace_batch_calculation():
    try:
        from app import create_app
        from app.database.database import db
        from app.Batch.model import Batch
        from app.Batch.controllers import BatchController
        from app.Investments.model import Investment
        
        app = create_app()
        with app.app_context():
            session = db.session
            
            # Trace Portfolio 3 in detail
            batch = session.query(Batch).filter(
                Batch.batch_name == "Portfolio 3"
            ).first()
            
            if not batch:
                print("Portfolio 3 not found!")
                return
            
            print("\n" + "=" * 130)
            print(f"DETAILED CALCULATION TRACE: {batch.batch_name}")
            print("=" * 130)
            
            investments = session.query(Investment).filter(
                Investment.batch_id == batch.id
            ).all()
            
            print(f"\nBatch ID: {batch.id}")
            print(f"Date Deployed: {batch.date_deployed}")
            print(f"Investments: {len(investments)}")
            print()
            
            running_total = 0.0
            
            for i, inv in enumerate(investments, 1):
                print(f"Investment {i}: {inv.investor_name}")
                print(f"  Batch ID: {inv.batch_id}")
                print(f"  Fund: {inv.fund.fund_name if inv.fund else inv.fund_name}")
                print(f"  Deposited: ${inv.amount_deposited:,.2f}")
                
                # Call the calculation method
                values = BatchController._calculate_batch_investment_values(inv, batch, session)
                
                print(f"  Calculated:")
                print(f"    Opening:       ${values['opening_balance']:,.2f}")
                print(f"    Current:       ${values['current_balance']:,.2f}")
                print(f"    Profit:        ${values['profit']:,.2f}")
                print(f"    Withdrawals:   ${values['withdrawals']:,.2f}")
                
                running_total += values['current_balance']
                print()
            
            print("=" * 130)
            print(f"Sum of all investment current balances: ${running_total:,.2f}")
            
            # Now call the batch method
            batch_total = BatchController._calculate_batch_current_standing(batch, session)
            print(f"Batch standing method result:           ${batch_total:,.2f}")
            
            print(f"\nMatch: {'✅ YES' if abs(running_total - batch_total) < 0.01 else '❌ NO'}")
            
            print(f"\nExpected: $185,877.00")
            print(f"Difference from expected: ${abs(running_total - 185877.00):,.2f}")
            
            print("=" * 130 + "\n")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    try:
        from app import create_app
        from app.database.database import db
        from app.Batch.model import Batch
        from app.Batch.controllers import BatchController
        from app.Investments.model import Investment
        
        app = create_app()
        with app.app_context():
            session = db.session
            
            # Trace Portfolio 3 in detail
            batch = session.query(Batch).filter(
                Batch.batch_name == "Portfolio 3"
            ).first()
            
            if not batch:
                print("Portfolio 3 not found!")
                return
            
            print("\n" + "=" * 130)
            print(f"DETAILED CALCULATION TRACE: {batch.batch_name}")
            print("=" * 130)
            
            investments = session.query(Investment).filter(
                Investment.batch_id == batch.id
            ).all()
            
            print(f"\nBatch ID: {batch.id}")
            print(f"Date Deployed: {batch.date_deployed}")
            print(f"Investments: {len(investments)}")
            print()
            
            running_total = 0.0
            
            for i, inv in enumerate(investments, 1):
                print(f"Investment {i}: {inv.investor_name}")
                print(f"  Batch ID: {inv.batch_id}")
                print(f"  Fund: {inv.fund.fund_name if inv.fund else inv.fund_name}")
                print(f"  Deposited: ${inv.amount_deposited:,.2f}")
                
                # Call the calculation method
                values = BatchController._calculate_batch_investment_values(inv, batch, session)
                
                print(f"  Calculated:")
                print(f"    Opening:       ${values['opening_balance']:,.2f}")
                print(f"    Current:       ${values['current_balance']:,.2f}")
                print(f"    Profit:        ${values['profit']:,.2f}")
                print(f"    Withdrawals:   ${values['withdrawals']:,.2f}")
                
                running_total += values['current_balance']
                print()
            
            print("=" * 130)
            print(f"Sum of all investment current balances: ${running_total:,.2f}")
            
            # Now call the batch method
            batch_total = BatchController._calculate_batch_current_standing(batch, session)
            print(f"Batch standing method result:           ${batch_total:,.2f}")
            
            print(f"\nMatch: {'✅ YES' if abs(running_total - batch_total) < 0.01 else '❌ NO'}")
            
            print(f"\nExpected: $185,877.00")
            print(f"Difference from expected: ${abs(running_total - 185877.00):,.2f}")
            
            print("=" * 130 + "\n")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    trace_batch_calculation()
