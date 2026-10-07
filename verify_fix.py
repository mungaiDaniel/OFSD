#!/usr/bin/env python3
"""Verify May calculations show correct investor breakdown"""
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
    
    print('=== VERIFIED MAY CALCULATIONS ===\n')
    
    may_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    may_end = datetime(2026, 5, 31, tzinfo=timezone.utc)
    rate = Decimal('0.05')
    
    # May for Atium
    print('MAY FOR ATIUM')
    print('═' * 70)
    may_atium = PortfolioValuationService.preview_epoch_for_fund_name(
        fund_name="Atium",
        start_date=may_start,
        end_date=may_end,
        performance_rate=rate,
        session=db.session,
    )
    
    print(f'Reconciliation Total: ${may_atium.get("reconciliation_total", 0):,.2f}')
    print(f'Total Start Balance: ${may_atium.get("total_start_balance", 0):,.2f}')
    print(f'Total Profit: ${may_atium.get("profit_total", 0):,.2f}')
    print()
    print('Investor Details:')
    for investor in may_atium.get("investor_breakdown", []):
        code = investor.get("internal_client_code")
        principal = investor.get("principal_before_start", 0)
        profit = investor.get("profit", 0)
        print(f'  {code:8} | Principal: ${principal:>10,.2f} | Profit: ${profit:>8,.2f}')
    
    print()
    print()
    
    # May for Axiom
    print('MAY FOR AXIOM')
    print('═' * 70)
    may_axiom = PortfolioValuationService.preview_epoch_for_fund_name(
        fund_name="Axiom",
        start_date=may_start,
        end_date=may_end,
        performance_rate=rate,
        session=db.session,
    )
    
    print(f'Reconciliation Total: ${may_axiom.get("reconciliation_total", 0):,.2f}')
    print(f'Total Start Balance: ${may_axiom.get("total_start_balance", 0):,.2f}')
    print(f'Total Profit: ${may_axiom.get("profit_total", 0):,.2f}')
    print()
    print('Investor Details:')
    for investor in may_axiom.get("investor_breakdown", []):
        code = investor.get("internal_client_code")
        principal = investor.get("principal_before_start", 0)
        profit = investor.get("profit", 0)
        print(f'  {code:8} | Principal: ${principal:>10,.2f} | Profit: ${profit:>8,.2f}')
    
    print('\n' + '═' * 70)
    total = float(may_atium.get("reconciliation_total", 0)) + float(may_axiom.get("reconciliation_total", 0))
    print(f'GRAND TOTAL (both funds): ${total:,.2f}')
