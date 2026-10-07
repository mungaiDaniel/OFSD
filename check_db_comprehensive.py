#!/usr/bin/env python3
"""Comprehensive database check to diagnose compound growth issue"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.Valuation.model import ValuationRun
    from app.Investments.model import EpochLedger
    from sqlalchemy import text
    
    print('=== FULL DATABASE DIAGNOSTIC ===\n')
    
    # Check all ValuationRun records
    print('ALL VALUATIONS (ValuationRun):')
    try:
        runs = db.session.execute(
            db.select(ValuationRun)
            .order_by(ValuationRun.epoch_start, ValuationRun.created_at)
        ).scalars().all()
        if runs:
            for r in runs:
                print(f'  {r.epoch_start.date()} to {r.epoch_end.date()} | Status: {r.status:<11} | Total: ${r.head_office_total:>12,.2f}')
        else:
            print('  (None found)')
    except Exception as e:
        print(f'  ERROR: {e}')
    
    print('\n\nALL EPOCH LEDGER ENTRIES (by date & investor):')
    print('Internal Code | Epoch End | Start Balance | Profit | End Balance | Period Profit %')
    print('-' * 90)
    try:
        ledgers = db.session.execute(
            db.select(EpochLedger)
            .order_by(EpochLedger.epoch_end, EpochLedger.internal_client_code)
        ).scalars().all()
        if ledgers:
            for el in ledgers:
                if el.start_balance and el.start_balance > 0:
                    pct = (float(el.profit) / float(el.start_balance)) * 100 if el.start_balance else 0
                else:
                    pct = 0
                print(f'{el.internal_client_code:<13} | {el.epoch_end.date()} | ${el.start_balance:>12,.2f} | ${el.profit:>7,.2f} | ${el.end_balance:>11,.2f} | {pct:>6.2f}%')
        else:
            print('  (None found)')
    except Exception as e:
        print(f'  ERROR: {e}')
    
    # Now test May's query
    print('\n\n=== TESTING MAY QUERY FOR APRIL DATA ===')
    print('When May (starting 2026-05-01) looks for previous epoch for AXIOM-001:')
    from datetime import datetime
    from app.Investments.model import Investment
    
    try:
        may_start = datetime(2026, 5, 1)
        prev_may = db.session.execute(
            db.select(EpochLedger)
            .where(EpochLedger.internal_client_code == 'AXIOM-001')
            .where(EpochLedger.epoch_end <= may_start)
            .order_by(EpochLedger.epoch_end.desc(), EpochLedger.id.desc())
        ).scalars().first()
        
        if prev_may:
            print(f'  ✓ FOUND previous epoch for AXIOM-001')
            print(f'    Epoch: {prev_may.epoch_start.date()} to {prev_may.epoch_end.date()}')
            print(f'    End Balance: ${prev_may.end_balance:,.2f}')
        else:
            print(f'  ✗ NOT FOUND - May would use default 0.00')
    except Exception as e:
        print(f'  ERROR: {e}')
