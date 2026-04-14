#!/usr/bin/env python3
"""Debug the compound growth calculation for May"""
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
    from app.Investments.model import EpochLedger
    
    print('=== DEBUGGING COMPOUND GROWTH FOR MAY ATIUM ===\n')
    
    may_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    fund_name = "Atium"
    
    # Manually check what _get_previous_epoch gets for each Atium investor in May
    print('Previous epoch lookup for May Atium investors:')
    print()
    
    for code in ['ATIUM-007', 'ATIUM-008']:
        prev_ledger = (
            db.session.query(EpochLedger)
            .filter(EpochLedger.internal_client_code == code)
            .filter(EpochLedger.fund_name == fund_name)
            .filter(EpochLedger.epoch_end <= may_start)
            .order_by(EpochLedger.epoch_end.desc(), EpochLedger.id.desc())
            .first()
        )
        
        if prev_ledger:
            print(f'{code}:')
            print(f'  Prev Epoch: {prev_ledger.epoch_start.date()} to {prev_ledger.epoch_end.date()}')
            print(f'  End Balance: ${prev_ledger.end_balance:,.2f}')
            print()
        else:
            print(f'{code}: NO PREVIOUS EPOCH FOUND')
            print()
