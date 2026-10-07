#!/usr/bin/env python
"""Debug script to check what's actually in Statement and cache tables"""
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment, PortfolioDisplayCache
from app.Valuation.model import Statement
from sqlalchemy import text
import json

app = create_app(Config)

with app.app_context():
    # Check Statement and PortfolioDisplayCache
    print("=" * 80)
    print("STATEMENT TABLE DATA")
    print("=" * 80)
    
    # Get all statements for a client (select first by code pattern)
    stmts = db.session.query(Statement, Investment).outerjoin(
        Investment, Statement.investor_id == Investment.id
    ).limit(20).all()
    
    print(f"Found {len(stmts)} Statement records\n")
    for stmt, inv in stmts[:10]:
        print(f"Statement ID {stmt.id}:")
        print(f"  Investor (Inv ID {stmt.investor_id}): {inv.investor_name if inv else '?'}")
        print(f"  Batch ID: {stmt.batch_id}")
        print(f"  Fund ID: {stmt.fund_id}")
        print(f"  Valuation Run: {stmt.valuation_run_id}")
        print(f"  Opening: ${stmt.opening_balance}")
        print(f"  Profit (performance_gain): ${stmt.performance_gain}")
        print(f"  Closing: ${stmt.closing_balance}")
        print()
    
    print("\n" + "=" * 80)
    print("PORTFOLIO DISPLAY CACHE")
    print("=" * 80)
    
    cache = db.session.query(PortfolioDisplayCache).first()
    if cache:
        print(f"Cache for: {cache.client_code}")
        print(f"Updated: {cache.updated_at}")
        
        holdings = json.loads(cache.holdings_display)
        print(f"\nHoldings ({len(holdings)}):")
        for h in holdings:
            print(f"  {h['batch_id']}: Profit=${h.get('profit')}, Balance=${h.get('current_balance')}")
    else:
        print("No cache found")
    
    print("\n" + "=" * 80)
    print("INVESTMENTS TABLE")
    print("=" * 80)
    
    invs = db.session.query(Investment).limit(10).all()
    print(f"Sample investments:")
    for inv in invs:
        print(f"  ID {inv.id}: {inv.investor_name} - Batch {inv.batch_id} - {inv.internal_client_code}")
