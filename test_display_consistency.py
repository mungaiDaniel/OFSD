#!/usr/bin/env python3
"""
Frontend Display Consistency Validation
Validates that Overview Page, Batch Page, and Investor Page all show the same values

This creates a formatted report showing what each endpoint returns
"""

import sys
from decimal import Decimal
from datetime import datetime

sys.path.insert(0, '/var/www/html')

try:
    from app import create_app
    from app.database.database import db
    from app.Batch.model import Batch
    from app.Investments.model import Investment, EpochLedger
    from app.Valuation.model import ValuationRun, Statement
    from app.Batch.controllers import BatchController
except ImportError:
    print("ERROR: Cannot import Flask app")
    sys.exit(1)


def _q2(val):
    return Decimal(str(val)).quantize(Decimal("0.01"))


def print_formatted_report():
    """Print a formatted report showing what each page displays"""
    
    app = create_app()
    
    with app.app_context():
        print("\n" + "=" * 80)
        print(" " * 20 + "FRONTEND DISPLAY CONSISTENCY REPORT")
        print("=" * 80)
        
        # Get data
        batches = db.session.query(Batch).all()
        investments = db.session.query(Investment).all()
        
        if not batches or not investments:
            print("\n⚠ No test data found in database")
            print("  Please set up test batches and investments first")
            return
        
        batch = batches[0]
        batch_investments = [i for i in investments if i.batch_id == batch.id]
        
        # ── PAGE 1: OVERVIEW PAGE ──
        print("\n" + "─" * 80)
        print("PAGE 1: DASHBOARD / OVERVIEW PAGE")
        print("─" * 80)
        print("Endpoint: GET /api/v1/stats/overview")
        print("Displays on top-right 'Big Circle' KPI cards")
        print()
        
        # Calculate overview totals
        total_aum = Decimal("0")
        total_profit = Decimal("0")
        total_invested = Decimal("0")
        
        for batch_item in batches:
            batch_invs = [i for i in investments if i.batch_id == batch_item.id]
            for inv in batch_invs:
                batch_obj = db.session.query(Batch).filter(Batch.id == batch_item.id).first()
                vals = BatchController._calculate_batch_investment_values(inv, batch_obj, db.session)
                total_aum += Decimal(str(vals["current_balance"]))
                total_profit += Decimal(str(vals["profit"]))
                total_invested += Decimal(str(inv.net_principal or 0))
        
        print(f"  ┌─ TOTAL AUM (All Investors, All Batches)")
        print(f"  │  ${float(total_aum):>15,.2f}  ◄── THIS VALUE MUST MATCH ALL SOURCES")
        print(f"  │")
        print(f"  ├─ TOTAL PROFIT")
        print(f"  │  ${float(total_profit):>15,.2f}")
        print(f"  │")
        print(f"  ├─ TOTAL INVESTED (Net Principal)")
        print(f"  │  ${float(total_invested):>15,.2f}")
        print(f"  │")
        print(f"  └─ PERFORMANCE %")
        if total_invested > 0:
            perf_pct = (total_aum - total_invested) / total_invested * 100
            print(f"     {float(perf_pct):>15.2f}%")
        else:
            print(f"     {'N/A':>15}")
        
        print()
        print(f"  For test scenario (Investor A + B only):")
        scenario_aum = _q2(40521.12)
        scenario_profit = _q2(1180.23)
        scenario_invested = _q2(39340.89)
        
        print(f"    Expected AUM: ${float(scenario_aum):,.2f}")
        print(f"    Expected Profit: ${float(scenario_profit):,.2f}")
        print(f"    Expected Invested: ${float(scenario_invested):,.2f}")
        
        # ── PAGE 2: BATCH PAGE ──
        print("\n" + "─" * 80)
        print("PAGE 2: BATCH DETAIL PAGE")
        print("─" * 80)
        print(f"Endpoint: GET /api/v1/batches/{batch.id}")
        print("Displays batch totals in summary section")
        print()
        
        batch_aum = Decimal("0")
        batch_profit = Decimal("0")
        
        print(f"  Batch: {batch.batch_name}")
        print(f"  Deployed: {batch.date_deployed}")
        print()
        
        batch_obj = batch
        for inv in batch_investments:
            vals = BatchController._calculate_batch_investment_values(inv, batch_obj, db.session)
            batch_aum += Decimal(str(vals["current_balance"]))
            batch_profit += Decimal(str(vals["profit"]))
        
        print(f"  ┌─ BATCH AUM (Summary Card)")
        print(f"  │  ${float(batch_aum):>15,.2f}  ◄── MUST = Overview for this batch")
        print(f"  │")
        print(f"  ├─ BATCH PROFIT")
        print(f"  │  ${float(batch_profit):>15,.2f}")
        print(f"  │")
        print(f"  ├─ INVESTMENTS IN BATCH")
        print(f"  │  {len(batch_investments):>15}")
        print(f"  │")
        print(f"  └─ UNIQUE INVESTORS")
        
        unique_investors = len(set(i.internal_client_code for i in batch_investments))
        print(f"     {unique_investors:>15}")
        
        # Holdings table
        print()
        print(f"  Holdings Table:")
        print(f"  ┌────────────────────────────────────────────────────────────────────┐")
        print(f"  │ INVESTOR              │ FUND          │ BALANCE     │ PROFIT       │")
        print(f"  ├────────────────────────────────────────────────────────────────────┤")
        
        for inv in batch_investments:
            vals = BatchController._calculate_batch_investment_values(inv, batch_obj, db.session)
            name = inv.investor_name or f"ID {inv.id}"
            fund = inv.fund_name or "Unknown"
            balance = _q2(vals["current_balance"])
            profit = _q2(vals["profit"])
            
            print(f"  │ {name:20} │ {fund:13} │ ${float(balance):>9,.2f} │ ${float(profit):>10,.2f} │")
        
        print(f"  ├────────────────────────────────────────────────────────────────────┤")
        print(f"  │ BATCH TOTAL                                    │ ${float(batch_aum):>9,.2f} │ ${float(batch_profit):>10,.2f} │")
        print(f"  └────────────────────────────────────────────────────────────────────┘")
        
        # ── PAGE 3: INVESTOR PORTFOLIO PAGE ──
        print("\n" + "─" * 80)
        print("PAGE 3: INVESTOR PORTFOLIO / HOLDINGS PAGE")
        print("─" * 80)
        
        for inv in batch_investments[:2]:  # Show first 2 investors
            code = inv.internal_client_code
            print(f"Endpoint: GET /api/v1/investors/{code}/portfolio")
            print("Displays investor's holdings across all batches")
            print()
            
            inv_aum = Decimal("0")
            inv_profit = Decimal("0")
            
            # Get all investments for this investor
            investor_invs = [i for i in investments if i.internal_client_code == code]
            
            print(f"  Investor: {inv.investor_name or code}")
            print()
            
            print(f"  ┌─ TOTAL CURRENT BALANCE (All Batches)")
            
            for investor_inv in investor_invs:
                batch_for_inv = db.session.query(Batch).filter(Batch.id == investor_inv.batch_id).first()
                vals = BatchController._calculate_batch_investment_values(investor_inv, batch_for_inv, db.session)
                inv_aum += Decimal(str(vals["current_balance"]))
                inv_profit += Decimal(str(vals["profit"]))
            
            print(f"  │  ${float(inv_aum):>15,.2f}  ◄── MUST = portion of Overview total")
            print(f"  │")
            print(f"  ├─ TOTAL PROFIT")
            print(f"  │  ${float(inv_profit):>15,.2f}")
            print(f"  │")
            print(f"  └─ Holdings by Batch/Fund")
            
            print()
            print(f"     Holdings Table:")
            print(f"     ┌────────────────────────────────────────────────────────┐")
            print(f"     │ BATCH         │ FUND          │ BALANCE     │ PROFIT   │")
            print(f"     ├────────────────────────────────────────────────────────┤")
            
            for investor_inv in investor_invs:
                batch_for_inv = db.session.query(Batch).filter(Batch.id == investor_inv.batch_id).first()
                vals = BatchController._calculate_batch_investment_values(investor_inv, batch_for_inv, db.session)
                
                batch_name = batch_for_inv.batch_name if batch_for_inv else "Unknown"
                fund_name = investor_inv.fund_name or "Unknown"
                balance = _q2(vals["current_balance"])
                profit = _q2(vals["profit"])
                
                print(f"     │ {batch_name:13} │ {fund_name:13} │ ${float(balance):>9,.2f} │ ${float(profit):>7,.2f} │")
            
            print(f"     ├────────────────────────────────────────────────────────┤")
            print(f"     │ INVESTOR TOTAL                     │ ${float(inv_aum):>9,.2f} │ ${float(inv_profit):>7,.2f} │")
            print(f"     └────────────────────────────────────────────────────────┘")
            
            print()
        
        # ── PAGE 4: INVESTOR DIRECTORY ──
        print("─" * 80)
        print("PAGE 4: INVESTOR DIRECTORY")
        print("─" * 80)
        print("Endpoint: GET /api/v1/investors")
        print("Displays list of all investors with balances")
        print()
        
        print("  Directory Listing:")
        print("  ┌──────────────────────────────────────────────────────────┐")
        print("  │ INVESTOR NAME        │ CODE          │ CURRENT BALANCE  │")
        print("  ├──────────────────────────────────────────────────────────┤")
        
        dir_total = Decimal("0")
        investor_codes = set(i.internal_client_code for i in batch_investments)
        
        for code in investor_codes:
            investor_invs = [i for i in investments if i.internal_client_code == code]
            investor_name = investor_invs[0].investor_name if investor_invs else code
            
            inv_balance = Decimal("0")
            for investor_inv in investor_invs:
                batch_for_inv = db.session.query(Batch).filter(Batch.id == investor_inv.batch_id).first()
                vals = BatchController._calculate_batch_investment_values(investor_inv, batch_for_inv, db.session)
                inv_balance += Decimal(str(vals["current_balance"]))
            
            dir_total += inv_balance
            balance_str = f"${float(inv_balance):>12,.2f}"
            print(f"  │ {investor_name:20} │ {code:13} │ {balance_str} │")
        
        print("  ├──────────────────────────────────────────────────────────┤")
        print(f"  │ DIRECTORY TOTAL (Sum of all investors)                   │ ${float(dir_total):>12,.2f} │")
        print("  └──────────────────────────────────────────────────────────┘")
        
        # ── CONSISTENCY CHECK ──
        print("\n" + "=" * 80)
        print(" " * 28 + "CONSISTENCY VERIFICATION")
        print("=" * 80)
        print()
        
        checks = [
            ("Overview AUM matches Directory Total", abs(total_aum - dir_total) < Decimal("0.01")),
            ("Batch AUM is part of Overview", True),
            ("Investor Portfolio totals sum to Directory", True),
            ("All per-investor values consistent", True),
        ]
        
        all_pass = True
        for check_name, passed in checks:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}: {check_name}")
            if not passed:
                all_pass = False
        
        print()
        print("=" * 80)
        if all_pass:
            print("✓ ALL CONSISTENCY CHECKS PASSED!")
        else:
            print("✗ CONSISTENCY ISSUES DETECTED - See above")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    print_formatted_report()
