#!/usr/bin/env python3
"""Check which ValuationRun each EpochLedger belongs to"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.Investments.model import EpochLedger
    from app.Valuation.model import ValuationRun
    
    print('=== VALUATION RUN <-> EPOCH LEDGER MAPPING ===\n')
    
    # Get all ValuationRuns
    runs = db.session.query(ValuationRun).order_by(ValuationRun.id).all()
    
    for run in runs:
        print(f'ValuationRun #{run.id}:')
        print(f'  Dates: {run.epoch_start.date()} to {run.epoch_end.date()}')
        print(f'  Status: {run.status}')
        print(f'  Head Office Total: ${run.head_office_total:,.2f}')
        print(f'  EpochLedger entries:')
        
        # Get all ledgers for this run
        ledgers = db.session.query(EpochLedger).filter(
            (EpochLedger.epoch_start == run.epoch_start) &
            (EpochLedger.epoch_end == run.epoch_end)
        ).all()
        if ledgers:
            total = 0
            fund_names = set()
            for el in ledgers:
                print(f'    {el.internal_client_code:8} | Fund: {el.fund_name:6} | End: ${el.end_balance:>12,.2f}')
                total += float(el.end_balance)
                fund_names.add(el.fund_name)
            print(f'  Sum of EpochLedger end_balances: ${total:,.2f}')
            print(f'  Contains funds: {", ".join(sorted(fund_names))}')
        else:
            print(f'    (No ledger entries found)')
        print()
