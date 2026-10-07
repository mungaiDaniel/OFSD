#!/usr/bin/env python
"""
Simple test to validate the holdings profit fix.
"""
from decimal import Decimal
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import PortfolioDisplayCache, Investment
from app.logic.portfolio_display_service import PortfolioDisplayAggregationService
import json
from sqlalchemy import func

app = create_app(Config)

with app.app_context():
    # Find AXIOM-001 investor code
    client_codes = db.session.query(func.distinct(Investment.internal_client_code)).filter(
        Investment.internal_client_code == 'AXIOM-001'
    ).all()
    
    if not client_codes:
        print("❌ AXIOM-001 not found")
        exit(1)
    
    test_code = client_codes[0][0]
    print(f"Testing with: {test_code}")
    
    # Rebuild cache
    print("Rebuilding cache...")
    try:
        PortfolioDisplayAggregationService.rebuild_cache(test_code, db.session)
        db.session.commit()
        print("✅ Rebuilt")
    except Exception as e:
        print(f"❌ Rebuild failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    
    # Get cache
    cache = db.session.query(PortfolioDisplayCache).filter(
        PortfolioDisplayCache.client_code == test_code
    ).first()
    
    if not cache:
        print("❌ No cache")
        exit(1)
    
    # Show holdings
    holdings = json.loads(cache.holdings_display)
    print(f"\nHoldings ({len(holdings)}):")
    for h in holdings:
        print(f"  {h['batch_id']}: Profit=${h.get('profit', 'N/A')}, Balance=${h.get('current_balance', 'N/A')}")
    
    # Check for bad values
    bad_profits = [h for h in holdings if h.get('profit') == '914.58']
    if bad_profits:
        print(f"\n❌ FAILED: Found {len(bad_profits)} holdings with profit=$914.58 (double-counted)")
        exit(1)
    else:
        print("\n✅ SUCCESS: No double-counted profits found!")
        exit(0)
