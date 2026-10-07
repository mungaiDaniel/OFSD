#!/usr/bin/env python
"""Check database directly with SQL"""
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from sqlalchemy import text

app = create_app(Config)

with app.app_context():
    try:
        # Query statements
        result = db.session.execute(text("""
            SELECT s.id, s.investor_id, s.batch_id, s.fund_id, s.performance_gain, s.closing_balance, s.created_at
            FROM statements s
            LIMIT 5
        """))
        
        print("Statements:")
        for row in result:
            print(f"  ID {row[0]}: Investor {row[1]}, Batch {row[2]}, Fund {row[3]}, Profit {row[4]}, Closing {row[5]}")
        
        # Query cache
        result = db.session.execute(text("""
            SELECT client_code, kpi_total_profit, holdings_display
            FROM portfolio_display_cache
            LIMIT 1
        """))
        
        print("\nCache:")
        for row in result:
            print(f"  Client: {row[0]}")
            print(f"  Total Profit: {row[1]}")
            import json
            holdings = json.loads(row[2])
            for h in holdings[:2]:
                print(f"    {h['batch_id']}: Profit {h.get('profit')}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
