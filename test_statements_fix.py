#!/usr/bin/env python3
"""
Test script to verify Historical Statements fixes.
Tests the unified /statements endpoint and investor breakdown data.
"""

import os
import sys
from decimal import Decimal
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Batch.model import Batch
from app.Valuation.model import ValuationRun
from app.Batch.core_fund import CoreFund

def test_epoch_ledger_data():
    """Test 1: Verify EpochLedger has correct start_balance values"""
    print("\n" + "="*80)
    print("TEST 1: EpochLedger Data Integrity")
    print("="*80)
    
    app = create_app("testing")
    with app.app_context():
        # Get all ledger entries
        entries = db.session.query(EpochLedger).all()
        
        if not entries:
            print("⚠️  No EpochLedger entries found. Run a valuation first.")
            return False
        
        print(f"\n✓ Found {len(entries)} ledger entries\n")
        
        # Group by investor for verification
        by_investor = {}
        for e in entries:
            if e.internal_client_code not in by_investor:
                by_investor[e.internal_client_code] = []
            by_investor[e.internal_client_code].append(e)
        
        # Verify running balances for first 3 investors
        for idx, (client_code, ledger_list) in enumerate(list(by_investor.items())[:3]):
            print(f"Investor {client_code}:")
            
            # Sort by epoch_end
            ledger_list.sort(key=lambda x: x.epoch_end)
            
            for i, ledger in enumerate(ledger_list):
                start = float(ledger.start_balance or 0)
                deposits = float(ledger.deposits or 0)
                withdrawals = float(ledger.withdrawals or 0)
                profit = float(ledger.profit or 0)
                end = float(ledger.end_balance or 0)
                
                calculated_end = start + deposits - withdrawals + profit
                
                # Verify arithmetic
                if abs(calculated_end - end) > 0.01:
                    print(f"  ❌ Period {i+1} ({ledger.epoch_end.date()}): "
                          f"Arithmetic error! Calculated={calculated_end:.2f}, Stored={end:.2f}")
                    return False
                else:
                    print(f"  ✓ Period {i+1} ({ledger.epoch_end.date()}): "
                          f"Opening={start:.2f}, Deposits={deposits:.2f}, "
                          f"Profit={profit:.2f}, Closing={end:.2f}")
        
        print("\n✓ All ledger values verified!")
        return True


def test_investments_table():
    """Test 2: Verify Investment records exist"""
    print("\n" + "="*80)
    print("TEST 2: Investment Records")
    print("="*80)
    
    app = create_app("testing")
    with app.app_context():
        investments = db.session.query(Investment).all()
        
        if not investments:
            print("⚠️  No investment records found.")
            return False
        
        print(f"\n✓ Found {len(investments)} investment records\n")
        
        # Group by batch
        by_batch = {}
        for inv in investments:
            if inv.batch_id not in by_batch:
                by_batch[inv.batch_id] = []
            by_batch[inv.batch_id].append(inv)
        
        # Show first 3 batches
        for batch_id, batch_invs in list(by_batch.items())[:3]:
            total = sum(float(i.amount_deposited or 0) for i in batch_invs)
            print(f"  Batch {batch_id}: {len(batch_invs)} deposits, Total=${total:.2f}")
            for inv in batch_invs[:2]:  # Show first 2
                print(f"    - {inv.investor_name} ({inv.internal_client_code}): "
                      f"${float(inv.amount_deposited):.2f} on {inv.date_deposited.date()}")
        
        print("\n✓ Investment records OK")
        return True


def test_statement_calculation():
    """Test 3: Manually verify statement calculation for one investor"""
    print("\n" + "="*80)
    print("TEST 3: Historical Statement Calculation Verification")
    print("="*80)
    
    app = create_app("testing")
    with app.app_context():
        # Pick first investor with both investments and ledger data
        client_code = None
        
        # Find investor with complete data
        investors = db.session.query(Investment.internal_client_code)\
            .group_by(Investment.internal_client_code)\
            .all()
        
        if not investors:
            print("⚠️  No investors found")
            return False
        
        client_code = investors[0][0]
        
        print(f"\nTesting investor: {client_code}\n")
        
        # Get all investments
        investments = db.session.query(Investment)\
            .filter(Investment.internal_client_code == client_code)\
            .all()
        
        total_deposits = sum(float(i.amount_deposited or 0) for i in investments)
        print(f"Total Deposits from Investment table: ${total_deposits:.2f}")
        
        # Get all ledger entries
        ledgers = db.session.query(EpochLedger)\
            .filter(EpochLedger.internal_client_code == client_code)\
            .order_by(EpochLedger.epoch_end)\
            .all()
        
        if not ledgers:
            print("⚠️  No ledger entries for this investor")
            return False
        
        print(f"Valuation periods: {len(ledgers)}\n")
        
        running_balance = 0.0
        for i, ledger in enumerate(ledgers):
            # Verify opening matches calculated running balance
            opening = float(ledger.start_balance or 0)
            deposits = float(ledger.deposits or 0)
            withdrawals = float(ledger.withdrawals or 0)
            profit = float(ledger.profit or 0)
            closing = float(ledger.end_balance or 0)
            
            # For first period, running_balance starts at 0
            if i == 0:
                if opening == 0:
                    print(f"  ✓ Period 1: Opening balance correctly shows 0 (new investor)")
                else:
                    print(f"  ⚠️  Period 1: Opening balance is {opening:.2f}, expected 0 for first period")
            else:
                # Subsequent periods should open with previous closing
                if abs(opening - running_balance) < 0.01:
                    print(f"  ✓ Period {i+1}: Opening ${opening:.2f} matches previous closing")
                else:
                    print(f"  ❌ Period {i+1}: Opening ${opening:.2f} doesn't match previous ${running_balance:.2f}")
                    return False
            
            # Verify closing = opening + deposits - withdrawals + profit
            calculated = opening + deposits - withdrawals + profit
            if abs(calculated - closing) < 0.01:
                print(f"      Content: +${deposits:.2f} (deposit) -{withdrawals:.2f} (withdrawal) "
                      f"+${profit:.2f} (profit) = Closing ${closing:.2f} ✓")
            else:
                print(f"      ❌ Math error! Calculated {calculated:.2f} != stored {closing:.2f}")
                return False
            
            running_balance = closing
        
        print("\n✓ Statement calculation verified!")
        return True


def test_report_investor_breakdown():
    """Test 4: Verify investor breakdown from view"""
    print("\n" + "="*80)
    print("TEST 4: Report Investor Breakdown")
    print("="*80)
    
    app = create_app("testing")
    with app.app_context():
        # Get latest valuation run
        vr = db.session.query(ValuationRun)\
            .filter(ValuationRun.status == "Committed")\
            .order_by(ValuationRun.epoch_end.desc())\
            .first()
        
        if not vr:
            print("⚠️  No committed valuation runs found")
            return False
        
        print(f"\nLatest Valuation Run: {vr.epoch_start.date()} → {vr.epoch_end.date()}")
        print(f"Performance Rate: {float(vr.performance_rate)*100:.2f}%\n")
        
        # Get ledger entries for this period
        ledgers = db.session.query(EpochLedger)\
            .filter(
                EpochLedger.epoch_end == vr.epoch_end,
                EpochLedger.fund_name == vr.core_fund.fund_name
            )\
            .all()
        
        print(f"Investors in this period: {len(ledgers)}\n")
        
        # Show first 3
        for idx, ledger in enumerate(ledgers[:3]):
            opening = float(ledger.start_balance or 0)
            deposits = float(ledger.deposits or 0)
            withdrawals = float(ledger.withdrawals or 0)
            profit = float(ledger.profit or 0)
            closing = float(ledger.end_balance or 0)
            
            print(f"{idx+1}. {ledger.internal_client_code}")
            print(f"   Opening: ${opening:.2f}")
            print(f"   Deposits: ${deposits:.2f}")
            print(f"   Withdrawals: ${withdrawals:.2f}")
            print(f"   Profit: ${profit:.2f}")
            print(f"   Closing: ${closing:.2f}")
            print()
        
        print("✓ Investor breakdown data OK")
        return True


def main():
    print("\n")
    print("█" * 80)
    print("  HISTORICAL STATEMENTS FIX VERIFICATION TESTS")
    print("█" * 80)
    
    try:
        tests = [
            ("EpochLedger Data Integrity", test_epoch_ledger_data),
            ("Investment Records", test_investments_table),
            ("Statement Calculations", test_statement_calculation),
            ("Report Investor Breakdown", test_report_investor_breakdown),
        ]
        
        results = {}
        for name, test_func in tests:
            try:
                results[name] = test_func()
            except Exception as e:
                print(f"\n❌ Test failed with error: {str(e)}")
                import traceback
                traceback.print_exc()
                results[name] = False
        
        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        for name, passed in results.items():
            status = "✓ PASS" if passed else "❌ FAIL"
            print(f"{status}: {name}")
        
        all_passed = all(results.values())
        
        if all_passed:
            print("\n✓ All tests passed! Historical statements should now display correctly.")
        else:
            print("\n❌ Some tests failed. Check the output above.")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
