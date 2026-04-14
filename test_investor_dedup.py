#!/usr/bin/env python3
"""
Test script to verify unique investor counting logic.
"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from app.database.database import db
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment
from sqlalchemy import func, distinct

app = create_app(Config)

with app.app_context():
    print("=" * 80)
    print("INVESTOR DEDUPLICATION TEST")
    print("=" * 80)
    print()
    
    # Test 1: Count unique investors in each batch
    print("Test 1: Unique Investor Counts by Batch")
    print("-" * 40)
    batches = db.session.query(Batch).all()
    
    for batch in batches:
        # Row count (old logic)
        row_count = db.session.query(Investment).filter(
            Investment.batch_id == batch.id
        ).count()
        
        # Unique count (new logic)
        unique_count = db.session.query(
            func.count(distinct(Investment.internal_client_code))
        ).filter(
            Investment.batch_id == batch.id
        ).scalar() or 0
        
        print(f"Batch: {batch.batch_name}")
        print(f"  Total investment rows: {row_count}")
        print(f"  Unique investors:     {unique_count}")
        
        if row_count == unique_count:
            print("  ✓ All investors have single entry")
        elif row_count > unique_count:
            print(f"  ⚠️  {row_count - unique_count} duplicate entries found")
        print()
    
    # Test 2: Portfolio aggregation - verify grouping
    print("\nTest 2: Portfolio Aggregation")
    print("-" * 40)
    
    # Get unique codes
    codes = db.session.query(distinct(Investment.internal_client_code)).all()
    
    for (code,) in codes[:3]:  # Test first 3 investors
        investments = db.session.query(Investment).filter(
            Investment.internal_client_code == code
        ).all()
        
        total_principal = sum(float(i.amount_deposited) for i in investments)
        
        # Group by batch/fund
        holdings = {}
        for inv in investments:
            batch_id = inv.batch_id
            fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
            key = (batch_id, fund_name)
            
            if key not in holdings:
                holdings[key] = {'count': 0, 'total': 0.0}
            holdings[key]['count'] += 1
            holdings[key]['total'] += float(inv.amount_deposited)
        
        print(f"Investor: {code}")
        print(f"  Total entries: {len(investments)}")
        print(f"  Total principal: ${total_principal:,.2f}")
        print(f"  Holdings (batch/fund breakdown):")
        for (batch_id, fund_name), data in holdings.items():
            print(f"    - Batch {batch_id}, Fund '{fund_name}': {data['count']} entries, ${data['total']:,.2f}")
        print()
    
    # Test 3: Fund-level unique counts
    print("\nTest 3: Fund-Level Unique Investor Counts")
    print("-" * 40)
    
    funds = db.session.query(CoreFund).filter(CoreFund.is_active == True).all()
    
    for fund in funds:
        # Row count
        row_count = db.session.query(Investment).filter(
            Investment.fund_id == fund.id
        ).count()
        
        # Unique count
        unique_count = db.session.query(
            func.count(distinct(Investment.internal_client_code))
        ).filter(
            Investment.fund_id == fund.id
        ).scalar() or 0
        
        print(f"Fund: {fund.fund_name}")
        print(f"  Total rows: {row_count}")
        print(f"  Unique:     {unique_count}")
        print()
    
    print("=" * 80)
    print("All tests completed!")
    print("=" * 80)
