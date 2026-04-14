#!/usr/bin/env python3
"""Simple database check using Flask shell approach"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app

# Create app properly
app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.Valuation.model import ValuationRun
    from app.Investments.model import EpochLedger
    
    print('=== CHECKING DATABASE STATE ===\n')
    
    print('COMMITTED VALUATIONS (ValuationRun):')
    try:
        runs = db.session.execute(db.select(ValuationRun).order_by(ValuationRun.epoch_start)).scalars().all()
        if runs:
            for r in runs:
                print(f'  {r.epoch_start.date()} to {r.epoch_end.date():<10} | Status: {r.status:<10} | Total: ${r.head_office_total}')
        else:
            print('  (None found)')
    except Exception as e:
        print(f'  ERROR: {e}')
    
    print('\nEPOCH LEDGER ENTRIES (by date & investor):')
    try:
        ledgers = db.session.execute(
            db.select(EpochLedger).order_by(EpochLedger.epoch_end, EpochLedger.internal_client_code)
        ).scalars().all()
        if ledgers:
            for el in ledgers:
                print(f'  {el.internal_client_code:<8} | {el.epoch_end.date()} | Start: ${el.start_balance:>12,.2f} | Profit: ${el.profit:>12,.2f} | End: ${el.end_balance:>12,.2f}')
        else:
            print('  (None found)')
    except Exception as e:
        print(f'  ERROR: {e}')
