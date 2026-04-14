#!/usr/bin/env python3
"""Check investment records to see why AXIOM is missing from May calc"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.Investments.model import Investment
    from sqlalchemy import func
    
    print('=== INVESTMENT RECORDS CHECK ===\n')
    
    print('All investments for "Atium" fund:')
    print('Internal Code | Batch ID | Fund ID | Fund Name | Amount | Wealth Manager | IFA | Active Start (earliest)')
    print('-' * 120)
    
    # Query Atium fund ID
    from app.Batch.core_fund import CoreFund
    atium = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == 'atium').first()
    axiom = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == 'axiom').first()
    
    print(f'\nCore Fund IDs: Atium={atium.id if atium else "None"}, Axiom={axiom.id if axiom else "None"}\n')
    
    # Get all investments
    all_inv = db.session.query(Investment).all()
    for inv in all_inv:
        active_start = inv.date_transferred or inv.date_deposited or 'None'
        print(f'{inv.internal_client_code:<13} | {inv.batch_id:<8} | {inv.fund_id or "NULL":<7} | {inv.fund_name or "NULL":<9} | ${inv.amount_deposited:>10,.2f} | {inv.wealth_manager or "NULL":<13} | {inv.IFA or "NULL":<10} | {active_start}')
