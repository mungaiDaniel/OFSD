#!/usr/bin/env python3
"""Simulate May valuation calculation to diagnose the issue"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from datetime import datetime, timezone

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.logic.valuation_service import PortfolioValuationService
    from decimal import Decimal
    
    print('=== SIMULATING MAY VALUATION ===\n')
    
    try:
        # May dates and assumptions (with timezone)
        may_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
        may_end = datetime(2026, 5, 31, tzinfo=timezone.utc)
        performance_rate = 0.05  # 5%
        
        print(f'Simulating: {may_start.date()} to {may_end.date()}, Rate: 5%')
        print()
        
        # Use preview for fund "Atium" (fund_id = 1)
        preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Atium",
            start_date=may_start,
            end_date=may_end,
            performance_rate=Decimal(performance_rate),
            session=db.session,
        )
        
        print('Preview Results:')
        print(f'  calculated_total: ${preview.get("calculated_total", 0):,.2f}')
        print(f'  reconciliation_total: ${preview.get("reconciliation_total", 0):,.2f}')
        print(f'  total_start_balance: ${preview.get("total_start_balance", 0):,.2f}')
        print(f'  total_deposits: ${preview.get("deposits_total", 0):,.2f}')
        print(f'  total_profit: ${preview.get("profit_total", 0):,.2f}')
        print(f'  excel_total: ${preview.get("excel_total", 0):,.2f}')
        
        print('\nInvestor Breakdown:')
        print(f'Keys in first investor: {list(preview.get("investor_breakdown", [{}])[0].keys()) if preview.get("investor_breakdown") else "None"}')
        for inv in preview.get("investor_breakdown", []):
            print(f'  {inv.get("internal_client_code", "?"):8} | Data: {inv}')
        
        # Expected reconciliation
        if preview.get("reconciliation_total"):
            print(f'\n✓ May calculation returned non-April values')
        else:
            print(f'\n✗ May calculation appears to have failed or returned 0')
            
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
