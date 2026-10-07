#!/usr/bin/env python
"""
TRACE THE EXACT SOURCE OF $914.58 profit
Compare what Historical Statements shows vs what Holdings is calculating
"""
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from sqlalchemy import text
import json

app = create_app(Config)

with app.app_context():
    print("\n" + "="*80)
    print("TRACING PROFIT CALCULATION: $914.58 vs $885.17")
    print("="*80)
    
    # Get the investor data
    result = db.session.execute(text("""
        SELECT 
            i.id, 
            i.investor_name, 
            i.internal_client_code,
            i.batch_id,
            b.batch_name,
            b.date_deployed
        FROM investments i
        JOIN batches b ON i.batch_id = b.id
        WHERE i.internal_client_code = '166173.0' OR i.investor_name LIKE '%Mung%'
        LIMIT 5
    """))
    
    inv_rows = result.fetchall()
    if not inv_rows:
        print("❌ No investors found")
        exit(1)
    
    for row in inv_rows:
        inv_id, inv_name, inv_code, batch_id, batch_name, deployed = row
        print(f"\n📋 Investor: {inv_name} ({inv_code})")
        print(f"   Investment ID: {inv_id}, Batch: {batch_name} (ID {batch_id}), Deployed: {deployed}")
        
        # Check STATEMENT table (what Historical Statements uses)
        print("\n   📊 STATEMENT table (per-investment per-batch):")
        result = db.session.execute(text(f"""
            SELECT s.id, s.opening_balance, s.performance_gain, s.closing_balance, 
                   s.closing_balance - s.opening_balance as calc_profit,
                   vr.epoch_end, vr.status
            FROM statements s
            JOIN valuation_runs vr ON s.valuation_run_id = vr.id
            WHERE s.investor_id = {inv_id} AND s.batch_id = {batch_id}
            ORDER BY vr.epoch_end DESC
            LIMIT 3
        """))
        
        stmt_rows = result.fetchall()
        for stmt_row in stmt_rows:
            stmt_id, opening, perf_gain, closing, calc_profit, epoch_end, status = stmt_row
            print(f"      Statement {stmt_id}: Opening ${opening:.2f}, Profit (perf_gain) ${perf_gain:.2f}, Closing ${closing:.2f} (Status: {status})")
        
        # Check EPOCHLEDGER table (what should be the source)
        print("\n   📈 EPOCHLEDGER table (per-fund per-period):")
        result = db.session.execute(text(f"""
            SELECT id, internal_client_code, fund_name, 
                   start_balance, profit, end_balance, performance_rate,
                   epoch_end
            FROM epoch_ledger
            WHERE LOWER(internal_client_code) = LOWER('{inv_code}')
            ORDER BY epoch_end DESC
            LIMIT 3
        """))
        
        epoch_rows = result.fetchall()
        for epoch_row in epoch_rows:
            epoch_id, client_code, fund, start, profit, end, perf_rate, epoch_end = epoch_row
            print(f"      EpochLedger {epoch_id}: Start ${start:.2f}, Profit ${profit:.2f}, End ${end:.2f}, Rate {perf_rate*100:.2f}% ({epoch_end})")
        
        # Now check what profit value is in the cache
        print("\n   💾 PORTFOLIO_DISPLAY_CACHE (what Holdings shows):")
        result = db.session.execute(text(f"""
            SELECT holdings_display
            FROM portfolio_display_cache
            WHERE client_code = '{inv_code}'
            LIMIT 1
        """))
        
        cache_row = result.fetchone()
        if cache_row:
            holdings = json.loads(cache_row[0])
            for h in holdings:
                if h['batch_id'] == batch_id:
                    print(f"      Batch {h['batch_id']}: Opening ${h['opening_amount']:.2f}, Profit ${h['profit']:.2f}, Performance {h['performance']:.2f}%")
                    print(f"      ❌ ISSUE: Showing ${h['profit']:.2f} but should be $885.17")

print("\n" + "="*80)
print("ANALYSIS:")
print("  If STATEMENT shows $885.17, that's correct ✓")
print("  If EPOCHLEDGER shows $885.17, that's correct ✓")
print("  If CACHE shows $914.58, something is OVERRIDING the calculation ❌")
print("="*80 + "\n")
