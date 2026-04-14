#!/usr/bin/env python3
"""Trace the exact calculation step by step"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from datetime import datetime, timezone
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    from app.logic.valuation_service import PortfolioValuationService as PVS
    from app.database.database import db
    from app.Investments.model import Investment, EpochLedger
    from app.Batch.core_fund import CoreFund
    from sqlalchemy import func
    from decimal import Decimal as D, ROUND_HALF_UP
    
    print('=== MANUAL CALCULATION FOR MAY ATIUM ===\n')
    
    may_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    may_end = datetime(2026, 5, 31, tzinfo=timezone.utc)
    rate = D('0.05')
    fund_name = "Atium"
    
    # Replicate the calculation steps
    period_days = (may_end - may_start).days + 1
    print(f'Period days: {period_days}')
    
    months = PVS._months_in_range(may_start, may_end)
    print(f'Months: {months}')
    
    months_detected = max(1, int(months))
    print(f'Months detected: {months_detected}')
    
    # Get core fund
    core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == fund_name.lower()).first()
    print(f'\nCore fund: {core.fund_name} (ID={core.id})')
    
    # Build investor inputs
    investor_inputs = PVS._build_investor_inputs(
        fund_id=core.id,
        fund_name=fund_name,
        start_date=may_start,
        end_date=may_end,
        session=db.session,
    )
    
    print(f'\nInvestor inputs:')
    for code, inp in investor_inputs.items():
        print(f'  {code}:')
        print(f'    principal_before_start: ${inp.principal_before_start:,.2f}')
        print(f'    deposits_during_period: ${inp.deposits_during_period:,.2f}')
        print(f'    weighted_capital: ${inp.weighted_capital:,.2f}')
    
    # Now apply compound growth logic
    print(f'\nApplying compound growth:')
    opening_weights_compounded = {}
    total_opening_active = D('0')
    
    for code, inp in investor_inputs.items():
        # Get previous epoch
        prev_ledger = (
            db.session.query(EpochLedger)
            .filter(EpochLedger.internal_client_code == code)
            .filter(EpochLedger.fund_name == fund_name)
            .filter(EpochLedger.epoch_end <= may_start)
            .order_by(EpochLedger.epoch_end.desc(), EpochLedger.id.desc())
            .first()
        )
        
        prev_end = D(str(prev_ledger.end_balance)) if prev_ledger else D('0')
        
        # Compounded opening = prev_end + principal_before_start
        opening_balance = (prev_end + inp.principal_before_start).quantize(D('0.01'), rounding=ROUND_HALF_UP)
        
        print(f'\n  {code}:')
        print(f'    Previous end balance: ${prev_end:,.2f}')
        print(f'    Principal before start: ${inp.principal_before_start:,.2f}')
        print(f'    Compounded opening: ${opening_balance:,.2f}')
        
        opening_active = opening_balance + inp.deposits_during_period - inp.withdrawals_during_period
        days_active = max(1, (may_end - may_start).days + 1)
        opening_weight = opening_active * (D(days_active) / D(period_days))
        
        opening_weights_compounded[code] = opening_weight
        total_opening_active += opening_active
        
        print(f'    Opening active: ${opening_active:,.2f}')
        print(f'    Opening weight: ${opening_weight:,.2f}')
    
    total_weighted = sum(opening_weights_compounded.values(), D('0'))
    total_profit = (total_opening_active * rate * D(months_detected)).quantize(D('0.01'), rounding=ROUND_HALF_UP)
    
    print(f'\nTotals:')
    print(f'  Total opening active capital: ${total_opening_active:,.2f}')
    print(f'  Total weighted capital for allocation: ${total_weighted:,.2f}')
    print(f'  Performance rate: {rate} ({float(rate)*100}%)')
    print(f'  Months detected: {months_detected}')
    print(f'  TOTAL PROFIT: ${total_profit:,.2f}')
    print(f'    = ${total_opening_active:,.2f} × {rate} × {months_detected}')
    
    closing = total_opening_active + total_profit
    print(f'\n  EXPECTED CLOSING: ${closing:,.2f}')
