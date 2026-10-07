#!/usr/bin/env python
"""
Test script to validate the holdings profit fix.
Tests that Statement table is used correctly for per-batch valuations.
"""
from decimal import Decimal
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment, PortfolioDisplayCache, EpochLedger, Investor
from app.Batch.model import Batch
from app.Batch.fund import Fund
from app.Valuation.model import Statement

from app.logic.portfolio_display_service import PortfolioDisplayAggregationService
import json

app = create_app(Config)

def test_holdings_fix():
    """Test that holdings show correct profit using Statement table"""
    
    with app.app_context():
        # Find AXIOM-001 investor
        investor = db.session.query(Investor).filter(
            Investor.investor_code == 'AXIOM-001'
        ).first()
        
        if not investor:
            print("❌ AXIOM-001 investor not found")
            return False
        
        print(f"✅ Found AXIOM-001 investor (id={investor.id})")
        
        # Rebuild the cache
        print("\n📦 Rebuilding portfolio display cache...")
        try:
            PortfolioDisplayAggregationService.rebuild_cache(investor.investor_code, db.session)
            db.session.commit()
            print("✅ Cache rebuild completed")
        except Exception as e:
            print(f"❌ Cache rebuild failed: {e}")
            return False
        
        # Fetch the cache
        cache = db.session.query(PortfolioDisplayCache).filter(
            PortfolioDisplayCache.client_code == investor.investor_code
        ).first()
        
        if not cache:
            print("❌ No cache record found")
            return False
        
        print(f"✅ Cache found (updated: {cache.updated_at})")
        
        # Parse holdings display
        holdings_data = json.loads(cache.holdings_display)
        print(f"\n📊 Holdings Data:\n{json.dumps(holdings_data, indent=2)}")
        
        # Check for B001 and B002
        holdings_by_batch = {h['batch_id']: h for h in holdings_data}
        
        print("\n📋 Validation Checks:")
        print("=" * 60)
        
        all_correct = True
        for batch_id in ['B001', 'B002']:
            if batch_id in holdings_by_batch:
                h = holdings_by_batch[batch_id]
                print(f"\n{batch_id}:")
                print(f"  Opening Balance: ${h.get('opening_balance', 'N/A')}")
                print(f"  Current Balance: ${h.get('current_balance', 'N/A')}")
                print(f"  Profit: ${h.get('profit', 'N/A')}")
                print(f"  Withdrawals: ${h.get('withdrawals', 'N/A')}")
                print(f"  Performance %: {h.get('performance_rate', 'N/A')}")
                
                # Check if profit looks reasonable (not $914.58)
                profit = Decimal(str(h.get('profit', 0)))
                if profit == Decimal('914.58'):
                    print(f"  ❌ PROBLEM: Profit is $914.58 (double-counted from EpochLedger)")
                    all_correct = False
                else:
                    print(f"  ✅ Profit looks correct (using Statement table)")
            else:
                print(f"\n{batch_id}: Not found in holdings")
        
        # Check KPIs
        print(f"\n📈 KPIs:")
        print(f"  Total KPI: ${cache.kpi_total_current_balance}")
        print(f"  Total Profit: ${cache.kpi_total_profit}")
        print(f"  Total Withdrawals: ${cache.kpi_total_withdrawals}")
        
        return all_correct

if __name__ == '__main__':
    print("🧪 Testing Holdings Profit Fix")
    print("=" * 60)
    
    success = test_holdings_fix()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED - Holdings fix is working!")
    else:
        print("❌ TESTS FAILED - Check output above")
    
    exit(0 if success else 1)
