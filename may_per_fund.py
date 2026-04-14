#!/usr/bin/env python3
"""Calculate May correctly for each fund separately"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from datetime import datetime, timezone
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    from app.logic.valuation_service import PortfolioValuationService
    from app.database.database import db
    
    print('=== MAY CALCULATIONS PER FUND ===\n')
    
    may_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    may_end = datetime(2026, 5, 31, tzinfo=timezone.utc)
    rate = Decimal('0.05')
    
    # May for Atium
    print('═' * 60)
    print('MAY FOR ATIUM (reference April 2-30 $210k)')
    print('═' * 60)
    try:
        may_atium = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Atium",
            start_date=may_start,
            end_date=may_end,
            performance_rate=rate,
            session=db.session,
        )
        
        print(f'Expected May Atium Total: ${may_atium.get("reconciliation_total", 0):,.2f}')
        print()
        print('Breakdown:')
        for investor in may_atium.get("investor_breakdown", []):
            code = investor.get("internal_client_code")
            start_bal = investor.get("principal_before_start", 0)
            profit = investor.get("profit", 0)
            print(f'  {code:8} | Principal: ${start_bal:>10,.2f} | Profit: ${profit:>8,.2f}')
        
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
    
    # May for Axiom
    print('\n')
    print('═' * 60)
    print('MAY FOR AXIOM (reference April 1-30 $157.5k)')
    print('═' * 60)
    try:
        may_axiom = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Axiom",
            start_date=may_start,
            end_date=may_end,
            performance_rate=rate,
            session=db.session,
        )
        
        print(f'Expected May Axiom Total: ${may_axiom.get("reconciliation_total", 0):,.2f}')
        print()
        print('Breakdown:')
        for investor in may_axiom.get("investor_breakdown", []):
            code = investor.get("internal_client_code")
            start_bal = investor.get("principal_before_start", 0)
            profit = investor.get("profit", 0)
            print(f'  {code:8} | Principal: ${start_bal:>10,.2f} | Profit: ${profit:>8,.2f}')
        
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
    
    # Grand total
    total_may = float(may_atium.get("reconciliation_total", 0)) + float(may_axiom.get("reconciliation_total", 0))
    print(f'\n\nGRAND TOTAL FOR MAY (both funds): ${total_may:,.2f}')
