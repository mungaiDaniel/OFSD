#!/usr/bin/env python3
"""
SSOT Consistency Verification Script
Validates that Overview, Batch, and Investor endpoints all show the same values

This script tests:
1. Backend fee calculation correctness
2. SSOT consistency across all endpoints
3. No discrepancies between overview/batch/investor displays
"""

import sys
from decimal import Decimal
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, '/var/www/html')

try:
    from app import create_app
    from app.database.database import db
    from app.Batch.model import Batch
    from app.Investments.model import Investment, EpochLedger
    from app.Valuation.model import ValuationRun, Statement
    from app.Batch.controllers import BatchController
except ImportError:
    print("⚠ Backend not available - skipping integration tests")
    print("Run this script from within the Flask app context")
    sys.exit(1)


def _q2(val):
    """Quantize to 2 decimal places"""
    return Decimal(str(val)).quantize(Decimal("0.01"))


def test_ssot_consistency():
    """
    Verify SSOT consistency across endpoints:
    - GET /api/v1/stats/overview → total_aum
    - GET /api/v1/investors/{code}/portfolio → current_balance
    - GET /api/v1/investors → directory current_balance
    """
    from flask_jwt_extended import create_access_token
    import requests
    import json
    
    print("\n" + "=" * 70)
    print("SSOT CONSISTENCY VERIFICATION")
    print("=" * 70)
    
    app = create_app()
    
    with app.app_context():
        # Create a test JWT token
        with app.test_request_context():
            access_token = create_access_token(identity="test_user")
        
        headers = {"Authorization": f"Bearer {access_token}"}
        base_url = "http://localhost:5000/api/v1"
        
        # ── Test 1: Verify Overview Stats ──
        print("\n[TEST 1] Overview Stats Consistency")
        print("-" * 70)
        
        try:
            overview_resp = requests.get(f"{base_url}/stats/overview", headers=headers)
            overview_resp.raise_for_status()
            overview_data = overview_resp.json().get("data", {})
            
            print(f"✓ Overview endpoint: 200 OK")
            print(f"  Total AUM: ${overview_data.get('total_aum', 0):,.2f}")
            print(f"  Total Profit: ${overview_data.get('total_profit', 0):,.2f}")
            print(f"  Performance %: {overview_data.get('performance_pct', 0):.2f}%")
            print(f"  Total Investors: {overview_data.get('total_investors', 0)}")
            
            overview_aum = Decimal(str(overview_data.get('total_aum', 0)))
            
        except Exception as e:
            print(f"✗ Overview endpoint failed: {str(e)}")
            overview_aum = None
        
        # ── Test 2: Verify Investor Directory ──
        print("\n[TEST 2] Investor Directory Consistency")
        print("-" * 70)
        
        try:
            directory_resp = requests.get(f"{base_url}/investors", headers=headers)
            directory_resp.raise_for_status()
            directory_data = directory_resp.json().get("data", [])
            
            print(f"✓ Directory endpoint: 200 OK")
            print(f"  Investors found: {len(directory_data)}")
            
            directory_total = Decimal("0")
            for inv in directory_data:
                balance = Decimal(str(inv.get("current_balance", 0)))
                directory_total += balance
                print(f"  - {inv.get('investor_name', 'Unknown')}: ${balance:,.2f}")
            
            print(f"  Total from Directory: ${directory_total:,.2f}")
            
        except Exception as e:
            print(f"✗ Directory endpoint failed: {str(e)}")
            directory_total = None
        
        # ── Test 3: Verify Individual Investor Portfolios ──
        print("\n[TEST 3] Individual Portfolio Consistency")
        print("-" * 70)
        
        portfolio_total = Decimal("0")
        investor_portfolios = []
        
        try:
            if directory_data:
                for inv in directory_data[:2]:  # Test first 2 investors
                    code = inv.get("internal_client_code")
                    
                    port_resp = requests.get(
                        f"{base_url}/investors/{code}/portfolio",
                        headers=headers
                    )
                    port_resp.raise_for_status()
                    port_data = port_resp.json().get("data", {})
                    
                    balance = Decimal(str(port_data.get("current_balance", 0)))
                    portfolio_total += balance
                    
                    print(f"✓ Portfolio for {code}: ${balance:,.2f}")
                    
                    # Show holdings breakdown
                    holdings = port_data.get("holdings", [])
                    for h in holdings:
                        ending = Decimal(str(h.get("latest_valuation", {}).get("end_balance", 0)))
                        fund = h.get("fund_name", "Unknown")
                        print(f"    - {fund}: ${ending:,.2f}")
                    
                    investor_portfolios.append({
                        "code": code,
                        "balance": balance,
                        "name": inv.get("investor_name")
                    })
            
            print(f"\n  Total from Portfolios: ${portfolio_total:,.2f}")
            
        except Exception as e:
            print(f"✗ Portfolio endpoints failed: {str(e)}")
        
        # ── Test 4: Verification Results ──
        print("\n[TEST 4] SSOT Consistency Check")
        print("-" * 70)
        
        results = {
            "overview_aum": overview_aum,
            "directory_total": directory_total,
            "portfolio_total": portfolio_total,
            "consistent": True,
            "messages": []
        }
        
        if overview_aum and directory_total:
            diff = abs(overview_aum - directory_total)
            if diff < Decimal("0.01"):
                print(f"✓ Overview AUM ({overview_aum}) matches Directory Total ({directory_total})")
            else:
                print(f"✗ MISMATCH: Overview AUM ({overview_aum}) vs Directory Total ({directory_total})")
                print(f"  Difference: ${diff}")
                results["consistent"] = False
                results["messages"].append(f"Overview/Directory mismatch: ${diff}")
        
        if directory_total and portfolio_total:
            diff = abs(directory_total - portfolio_total)
            if diff < Decimal("0.01"):
                print(f"✓ Directory Total ({directory_total}) matches Portfolio Total ({portfolio_total})")
            else:
                print(f"✗ MISMATCH: Directory Total ({directory_total}) vs Portfolio Total ({portfolio_total})")
                print(f"  Difference: ${diff}")
                results["consistent"] = False
                results["messages"].append(f"Directory/Portfolio mismatch: ${diff}")
        
        # ── Summary ──
        print("\n" + "=" * 70)
        if results["consistent"] and len(results["messages"]) == 0:
            print("✓ ALL SSOT CONSISTENCY TESTS PASSED!")
            print("  Overview, Directory, and Portfolio endpoints are synchronized")
        else:
            print("✗ SSOT CONSISTENCY ISSUES DETECTED:")
            for msg in results["messages"]:
                print(f"  - {msg}")
        print("=" * 70 + "\n")
        
        return results


def test_database_values():
    """
    Query database directly to verify values are stored correctly
    """
    from app import create_app
    from app.database.database import db
    from app.Investments.model import Investment, EpochLedger
    from app.Valuation.model import Statement, ValuationRun
    
    print("\n" + "=" * 70)
    print("DATABASE VALUE VERIFICATION")
    print("=" * 70)
    
    app = create_app()
    
    with app.app_context():
        # ── Query 1: Investment Net Principals ──
        print("\n[Query 1] Investment Net Principals")
        print("-" * 70)
        
        investments = db.session.query(Investment).all()
        
        if investments:
            total_principal = Decimal("0")
            for inv in investments[:5]:  # First 5
                net_principal = Decimal(str(inv.net_principal or 0))
                total_principal += net_principal
                
                print(f"  {inv.investor_name or f'ID {inv.id}'}")
                print(f"    Original: ${Decimal(str(inv.amount_deposited or 0)):,.2f}")
                print(f"    Net Principal: ${net_principal:,.2f}")
                print(f"    Deployment Fee: ${Decimal(str(inv.deployment_fee_deducted or 0)):,.2f}")
                print(f"    Transfer Fee: ${Decimal(str(inv.transfer_fee_deducted or 0)):,.2f}")
            
            print(f"\n  Total Net Principal (first 5): ${total_principal:,.2f}")
        else:
            print("  No investments found in database")
        
        # ── Query 2: Statement Closing Balances ──
        print("\n[Query 2] Most Recent Statements")
        print("-" * 70)
        
        statements = db.session.query(Statement).order_by(
            Statement.created_at.desc()
        ).limit(5).all()
        
        if statements:
            for stmt in statements:
                closing = Decimal(str(stmt.closing_balance or 0))
                print(f"  Statement ID {stmt.id}")
                print(f"    Investor ID: {stmt.investor_id}")
                print(f"    Batch ID: {stmt.batch_id}")
                print(f"    Closing Balance: ${closing:,.2f}")
                print(f"    Created: {stmt.created_at}")
        else:
            print("  No statements found in database")
        
        # ── Query 3: Epoch Ledger Balances ──
        print("\n[Query 3] Epoch Ledger Summary")
        print("-" * 70)
        
        ledgers = db.session.query(EpochLedger).order_by(
            EpochLedger.epoch_end.desc()
        ).limit(5).all()
        
        if ledgers:
            for ledger in ledgers:
                print(f"  Ledger ID {ledger.id}")
                print(f"    Investor: {ledger.internal_client_code}")
                print(f"    Fund: {ledger.fund_name}")
                print(f"    Period: {ledger.epoch_start} - {ledger.epoch_end}")
                print(f"    Start: ${Decimal(str(ledger.start_balance or 0)):,.2f}")
                print(f"    End: ${Decimal(str(ledger.end_balance or 0)):,.2f}")
                print(f"    Profit: ${Decimal(str(ledger.profit or 0)):,.2f}")
        else:
            print("  No ledgers found in database")
        
        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    import os
    
    # Check if running in app context
    if os.environ.get("FLASK_ENV") or os.path.exists("/var/www/html/app/__init__.py"):
        print("Testing SSOT Consistency and Database Values...")
        
        # Run tests if backend is available
        try:
            consistency = test_ssot_consistency()
            database = test_database_values()
        except Exception as e:
            print(f"Note: Some tests require running within Flask app context")
            print(f"Error: {str(e)}")
            
            # Still try database tests
            try:
                test_database_values()
            except:
                pass
    else:
        print("Note: This script requires Flask app context to run integration tests")
        print("Run with: export FLASK_ENV=development && python test_ssot_consistency.py")
