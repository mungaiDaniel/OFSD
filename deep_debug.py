#!/usr/bin/env python3
"""Deep debug - trace exactly what preview_epoch_for_fund_name returns"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from datetime import datetime, timezone
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.logic.valuation_service import PortfolioValuationService
    from app.Investments.model import EpochLedger, Investment
    from app.Batch.core_fund import CoreFund
    from sqlalchemy import func
    
    print('=' * 80)
    print('DEEP DEBUG: MAY ATIUM CALCULATION')
    print('=' * 80)
    print()
    
    # Dates
    may_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    may_end = datetime(2026, 5, 31, tzinfo=timezone.utc)
    
    print(f'Period: {may_start.date()} to {may_end.date()}')
    print()
    
    # Step 1: Check investments
    print('STEP 1: Investments on record')
    print('-' * 80)
    atium_core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == 'atium').first()
    investments = db.session.query(Investment).filter(Investment.fund_id == atium_core.id).all()
    for inv in investments:
        print(f'  {inv.internal_client_code}: ${inv.amount_deposited}, deposited {inv.date_deposited.date()}')
    print()
    
    # Step 2: Check previous epoch
    print('STEP 2: Previous epoch data (April)')
    print('-' * 80)
    for inv in investments:
        prev = db.session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == inv.internal_client_code,
            EpochLedger.fund_name == 'Atium',
            EpochLedger.epoch_end <= may_start
        ).order_by(EpochLedger.epoch_end.desc()).first()
        
        if prev:
            print(f'  {inv.internal_client_code}:')
            print(f'    Epoch: {prev.epoch_start.date()} to {prev.epoch_end.date()}')
            print(f'    Start: ${prev.start_balance}')
            print(f'    End: ${prev.end_balance}')
        else:
            print(f'  {inv.internal_client_code}: NO PREVIOUS EPOCH')
    print()
    
    # Step 3: Call preview_epoch_for_fund_name
    print('STEP 3: Calling preview_epoch_for_fund_name')
    print('-' * 80)
    
    try:
        preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Atium",
            start_date=may_start,
            end_date=may_end,
            performance_rate=Decimal('0.05'),
            session=db.session,
        )
        
        print(f'Reconciliation Total: ${preview.get("reconciliation_total", 0):,.2f}')
        print(f'Total Open Capital: ${preview.get("total_open_capital", 0):,.2f}')
        print(f'Total Weighted Capital: ${preview.get("total_weighted_capital", 0):,.2f}')
        print(f'Total Profit: ${preview.get("profit_total", 0):,.2f}')
        print()
        
        print('Investor Breakdown:')
        for inv_data in preview.get("investor_breakdown", []):
            print(f'  Code: {inv_data.get("internal_client_code")}')
            print(f'    principal_before_start: ${inv_data.get("principal_before_start", 0):,.2f}')
            print(f'    deposits_during: ${inv_data.get("deposits_during_period", 0):,.2f}')
            print(f'    withdrawals_during: ${inv_data.get("withdrawals_during_period", 0):,.2f}')
            print(f'    active_capital: ${inv_data.get("active_capital", 0):,.2f}')
            print(f'    weighted_capital: ${inv_data.get("weighted_capital", 0):,.2f}')
            print(f'    profit: ${inv_data.get("profit", 0):,.2f}')
            print()
        
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
    
    print('=' * 80)
