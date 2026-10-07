#!/usr/bin/env python
"""Direct debug of cache rebuild"""
import logging
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment, PortfolioDisplayCache
from app.logic.portfolio_display_service import PortfolioDisplayAggregationService
from sqlalchemy import text
import json

# Enable logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

app = create_app(Config)

with app.app_context():
    print("\n" + "="*80)
    print("CHECKING DATABASE STATE")
    print("="*80)
    
    # Get distinct internal_client_codes
    codes = db.session.query(Investment.internal_client_code).distinct().limit(1).all()
    if not codes:
        print("No investments found")
        exit(1)
    
    test_code = codes[0][0]
    print(f"Testing with code: {test_code}")
    
    # Check current Statement data
    print("\nChecking Statement table for this investor...")
    result = db.session.execute(text(f"""
        SELECT s.id, s.investor_id, s.batch_id, s.fund_id, s.valuation_run_id, 
               s.performance_gain, s.opening_balance, s.closing_balance
        FROM statements s  
        JOIN investments i ON s.investor_id = i.id
        WHERE i.internal_client_code = '{test_code}'
        ORDER BY s.batch_id, s.valuation_run_id DESC
        LIMIT 20
    """))
    
    stmts = result.fetchall()
    print(f"Found {len(stmts)} Statement rows:")
    for row in stmts:
        print(f"  ID {row[0]:4} | Inv {row[1]:4} | Batch {row[2]:4} | Fund {row[3]:4} | VR {row[4]:4} | Profit ${row[5]:10.2f} | Open ${row[6]:.2f} | Close ${row[7]:.2f}")
    
    # Check what batches exist for this investor
    print("\nBatches for this investor:")
    result = db.session.execute(text(f"""
        SELECT DISTINCT b.id, b.batch_name, COUNT(i.id) as inv_count
        FROM investments i
        JOIN batches b ON i.batch_id = b.id
        WHERE i.internal_client_code = '{test_code}'
        GROUP BY b.id, b.batch_name
        ORDER BY b.id
    """))
    
    batches = result.fetchall()
    for batch_id, batch_name, count in batches:
        print(f"  Batch {batch_id:4}: {batch_name:20} ({count} investments)")
    
    # Now rebuild cache and check result
    print("\n" + "="*80)
    print("REBUILDING CACHE")
    print("="*80)
    
    # Clear cache first
    db.session.execute(text("DELETE FROM portfolio_display_cache WHERE client_code = %s"), [(test_code,)])
    db.session.commit()
    print(f"Cleared cache for {test_code}")
    
    # Rebuild
    cache = PortfolioDisplayAggregationService.rebuild_cache(test_code, db.session)
    db.session.commit()
    
    if cache:
        print(f"✅ Cache rebuilt: {cache.updated_at}")
        holdings = json.loads(cache.holdings_display)
        print(f"\nHoldings ({len(holdings)}):")
        for h in holdings:
            print(f"  Batch {h['batch_id']:4}: Opening ${h.get('opening_balance'): , Profit ${h.get('profit'):10.2f}, Balance ${h.get('current_balance'):10.2f}")
    else:
        print("❌ Cache rebuild returned None")
