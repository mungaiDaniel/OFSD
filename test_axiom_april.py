#!/usr/bin/env python3
import sys
sys.path.insert(0,'.')
from config import DevelopmentConfig as Config
from main import create_app
from datetime import datetime, timezone
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    from app.logic.valuation_service import PortfolioValuationService
    from app.database.database import db
    
    preview = PortfolioValuationService.preview_epoch_for_fund(
        fund_id=2,
        start_date=datetime(2026,4,1,tzinfo=timezone.utc),
        end_date=datetime(2026,4,30,tzinfo=timezone.utc),
        performance_rate=Decimal('0.05'),
        session=db.session,
    )
    print('== Axiom April Preview ==')
    print(preview)
