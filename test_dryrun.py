#!/usr/bin/env python3
"""Test the actual dry-run endpoint to see the exact error"""
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
    
    print('=== TESTING DRY-RUN FOR MAY ===\n')
    
    # Test for Atium only (fund_id=1)
    try:
        preview_atium = PortfolioValuationService.preview_epoch_for_fund(
            fund_id=1,
            start_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 5, 31, tzinfo=timezone.utc),
            performance_rate=Decimal('0.05'),
            session=db.session,
        )
        
        print('Atium Fund (ID=1) May Preview:')
        print(f'  Reconciliation Total: ${preview_atium.get("reconciliation_total", 0):,.2f}')
        
    except Exception as e:
        print(f'Atium ERROR: {e}')
    
    # Test for Axiom  (fund_id=2)
    try:
        preview_axiom = PortfolioValuationService.preview_epoch_for_fund(
            fund_id=2,
            start_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 5, 31, tzinfo=timezone.utc),
            performance_rate=Decimal('0.05'),
            session=db.session,
        )
        
        print('\nAxiom Fund (ID=2) May Preview:')
        print(f'  Reconciliation Total: ${preview_axiom.get("reconciliation_total", 0):,.2f}')
        
    except Exception as e:
        print(f'Axiom ERROR: {e}')
    
    # Combined via fund_name
    try:
        preview_by_name = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Atium",
            start_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 5, 31, tzinfo=timezone.utc),
            performance_rate=Decimal('0.05'),
            session=db.session,
        )
        
        print('\nAtium by Name May Preview:')
        print(f'  Reconciliation Total: ${preview_by_name.get("reconciliation_total", 0):,.2f}')
        
    except Exception as e:
        print(f'Atium by Name ERROR: {e}')
