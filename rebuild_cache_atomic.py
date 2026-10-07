#!/usr/bin/env python
"""Clear cache and force rebuild with atomic batching fix"""
import logging
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import PortfolioDisplayCache
from app.logic.portfolio_display_service import PortfolioDisplayAggregationService
from sqlalchemy import text
import json

logging.basicConfig(level=logging.INFO)

app = create_app(Config)

with app.app_context():
    print("\n" + "="*80)
    print("CLEARING CACHE AND REBUILDING WITH ATOMIC BATCHING FIX")
    print("="*80)
    
    # Clear all cache
    db.session.execute(text("DELETE FROM portfolio_display_cache"))
    db.session.commit()
    print("✅ Cache cleared")
    
    # Get all unique client codes
    from app.Investments.model import Investment
    from sqlalchemy import func
    codes = db.session.query(func.distinct(Investment.internal_client_code)).limit(5).all()
    
    print(f"\nFound {len(codes)} investor codes. Rebuilding caches...\n")
    
    rebuild_count = 0
    for code_tuple in codes:
        code = code_tuple[0]
        try:
            cache = PortfolioDisplayAggregationService.rebuild_cache(code, db.session)
            if cache:
                holdings = json.loads(cache.holdings_display)
                print(f"📦 {code}:")
                for h in holdings:
                    print(f"  {h['batch_id']:4s}: Opening ${h['opening_balance']:10.2f}  Profit ${h['profit']:10.2f}  Balance ${h['current_balance']:10.2f}  Performance {h.get('performance_rate', 0):5.2f}%")
                rebuild_count += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    db.session.commit()
    print(f"\n✅ Rebuilt {rebuild_count} caches")
    print("\n" + "="*80)
    print("KEY CHANGES:")
    print("  - B001 performance rate should now be STABLE at 3.00% (not 3.10%)")
    print("  - B002 performance rate should be independent of B001")
    print("  - Profit values should match Historical Statements")
    print("="*80)
