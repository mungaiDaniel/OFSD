#!/usr/bin/env python3
"""
Specific Scenario Test: Investor A & B Validation
Tests the specific scenario provided by the user:
- Investor A: $30,000 → $30,390.84
- Investor B: $10,000 → $10,130.28
- Batch Total: $40,000 → $40,521.12

This script:
1. Queries the database for investments matching the scenario
2. Validates the fee calculations
3. Verifies SSOT returns match database values
"""

import sys
from decimal import Decimal

sys.path.insert(0, '/var/www/html')

try:
    from app import create_app
    from app.database.database import db
    from app.Batch.model import Batch
    from app.Investments.model import Investment, EpochLedger, Withdrawal
    from app.Valuation.model import ValuationRun, Statement
    from app.Batch.controllers import BatchController
except ImportError:
    print("ERROR: Cannot import Flask app - run from within backend directory")
    sys.exit(1)


def _q2(val):
    return Decimal(str(val)).quantize(Decimal("0.01"))


def find_scenario_batch():
    """Find or create a batch with Investor A & B scenario"""
    app = create_app()
    
    with app.app_context():
        print("\n" + "=" * 70)
        print("SCENARIO VERIFICATION: Investor A & B")
        print("=" * 70)
        
        # Find batches
        batches = db.session.query(Batch).all()
        
        if not batches:
            print("\n✗ No batches found in database")
            print("  Please create a batch and add investments first")
            return None
        
        print(f"\nFound {len(batches)} batch(es) in database:")
        
        for batch in batches:
            print(f"\n  Batch: {batch.batch_name} (ID: {batch.id})")
            
            # Get investments in batch
            investments = db.session.query(Investment).filter(
                Investment.batch_id == batch.id
            ).all()
            
            print(f"    Investments: {len(investments)}")
            
            total_deposit = Decimal("0")
            for inv in investments:
                deposit = Decimal(str(inv.amount_deposited or 0))
                net_principal = Decimal(str(inv.net_principal or 0))
                total_deposit += deposit
                
                print(f"      - {inv.investor_name or f'ID {inv.id}'}")
                print(f"        Deposit: ${deposit:,.2f}")
                print(f"        Net Principal: ${net_principal:,.2f}")
            
            print(f"    Total Deposits: ${total_deposit:,.2f}")
            
            # Check if this matches scenario (2 investors with ~30K and ~10K)
            if len(investments) >= 2 and (total_deposit > 39000 and total_deposit < 41000):
                print(f"\n    → This batch MATCHES the scenario!")
                return batch, investments


def validate_scenario_batch(batch, investments):
    """Validate the fee calculations and valuations"""
    
    app = create_app()
    
    with app.app_context():
        print("\n" + "=" * 70)
        print("DETAILED CALCULATION VALIDATION")
        print("=" * 70)
        
        # Expected values
        expected = {
            "Investor A": {
                "deposit": 30000.00,
                "net_principal": 29505.67,
                "profit": 885.17,
                "ending": 30390.84,
            },
            "Investor B": {
                "deposit": 10000.00,
                "net_principal": 9835.22,
                "profit": 295.06,
                "ending": 10130.28,
            },
            "batch_ending": 40521.12,
        }
        
        # ── Validate Deposits & Net Principals ──
        print("\n[Step 1] Deposit & Fee Validation")
        print("-" * 70)
        
        inv_map = {}
        total_deposit = Decimal("0")
        total_net = Decimal("0")
        
        for i, inv in enumerate(investments[:2], 1):
            investor_name = inv.investor_name or f"Investor {['A', 'B'][i-1]}"
            deposit = _q2(inv.amount_deposited or 0)
            deployment_fee = _q2(inv.deployment_fee_deducted or 0)
            transfer_fee = _q2(inv.transfer_fee_deducted or 0)
            net_principal = _q2(inv.net_principal or 0)
            
            total_deposit += deposit
            total_net += net_principal
            
            inv_map[investor_name] = {
                "deposit": float(deposit),
                "deployment_fee": float(deployment_fee),
                "transfer_fee": float(transfer_fee),
                "net_principal": float(net_principal),
            }
            
            print(f"\n  {investor_name}:")
            print(f"    Deposit: ${float(deposit):,.2f}")
            print(f"    Transfer Fee: ${float(transfer_fee):,.2f}")
            print(f"    Deployment Fee (1.5%): ${float(deployment_fee):,.2f}")
            print(f"    Net Principal: ${float(net_principal):,.2f}")
            
            # Validate against expected
            if investor_name in expected:
                exp_net = expected[investor_name]["net_principal"]
                if abs(float(net_principal) - exp_net) < 0.01:
                    print(f"    ✓ Matches expected: ${exp_net:,.2f}")
                else:
                    print(f"    ✗ MISMATCH! Expected: ${exp_net:,.2f}")
        
        print(f"\nBatch Totals:")
        print(f"  Total Deposits: ${float(total_deposit):,.2f}")
        print(f"  Total Net Principal: ${float(total_net):,.2f}")
        expected_batch_net = 39340.89
        if abs(float(total_net) - expected_batch_net) < 0.01:
            print(f"  ✓ Matches expected: ${expected_batch_net:,.2f}")
        else:
            print(f"  ✗ MISMATCH! Expected: ${expected_batch_net:,.2f}")
        
        # ── Validate Statements ──
        print("\n[Step 2] Statement Valuation (3% Performance)")
        print("-" * 70)
        
        statements = db.session.query(Statement).filter(
            Statement.batch_id == batch.id
        ).all()
        
        if not statements:
            print("  ⚠ No statements found - creating test scenario")
            print("  Need to: 1) Create ValuationRun, 2) Run valuation, 3) Commit")
        else:
            total_closing = Decimal("0")
            total_profit = Decimal("0")
            
            for stmt in statements[:2]:
                investor_id = stmt.investor_id
                
                # Find matching investment
                inv = next((i for i in investments if i.id == investor_id), None)
                if not inv:
                    continue
                
                investor_name = inv.investor_name or "Unknown"
                
                opening = _q2(stmt.start_balance or 0)
                closing = _q2(stmt.closing_balance or 0)
                profit = closing - opening
                total_closing += closing
                total_profit += profit
                
                print(f"\n  {investor_name} (Statement {stmt.id}):")
                print(f"    Opening: ${float(opening):,.2f}")
                print(f"    Closing: ${float(closing):,.2f}")
                print(f"    Profit: ${float(profit):,.2f}")
                
                # Validate against expected
                if investor_name in expected:
                    exp_end = expected[investor_name]["ending"]
                    if abs(float(closing) - exp_end) < 0.01:
                        print(f"    ✓ Matches expected: ${exp_end:,.2f}")
                    else:
                        print(f"    ✗ MISMATCH! Expected: ${exp_end:,.2f}")
            
            print(f"\nBatch Statement Totals:")
            print(f"  Total Closing: ${float(total_closing):,.2f}")
            print(f"  Total Profit: ${float(total_profit):,.2f}")
            
            exp_batch_end = expected["batch_ending"]
            if abs(float(total_closing) - exp_batch_end) < 0.01:
                print(f"  ✓ Matches expected: ${exp_batch_end:,.2f}")
            else:
                print(f"  ✗ MISMATCH! Expected: ${exp_batch_end:,.2f}")
        
        # ── Validate SSOT Consistency ──
        print("\n[Step 3] SSOT Endpoint Consistency")
        print("-" * 70)
        
        batch_total_from_ssot = Decimal("0")
        
        for inv in investments:
            batch_obj = db.session.query(Batch).filter(Batch.id == batch.id).first()
            inv_values = BatchController._calculate_batch_investment_values(
                inv, batch_obj, db.session
            )
            current_balance = _q2(inv_values["current_balance"])
            batch_total_from_ssot += current_balance
            
            print(f"\n  {inv.investor_name or f'ID {inv.id}'}")
            print(f"    SSOT Current Balance: ${float(current_balance):,.2f}")
            
            # Find in expected based on deposit amount
            deposit = Decimal(str(inv.amount_deposited or 0))
            if deposit > 25000:  # Investor A
                exp_ending = expected["Investor A"]["ending"]
            else:  # Investor B
                exp_ending = expected["Investor B"]["ending"]
            
            if abs(float(current_balance) - exp_ending) < 0.01:
                print(f"    ✓ Matches expected: ${exp_ending:,.2f}")
            else:
                print(f"    ✗ MISMATCH! Expected: ${exp_ending:,.2f}")
        
        print(f"\nSSO Total: ${float(batch_total_from_ssot):,.2f}")
        if abs(float(batch_total_from_ssot) - expected["batch_ending"]) < 0.01:
            print(f"✓ Matches expected batch total: ${expected['batch_ending']:,.2f}")
        else:
            print(f"✗ MISMATCH! Expected: ${expected['batch_ending']:,.2f}")
        
        # ── Final Summary ──
        print("\n" + "=" * 70)
        print("SCENARIO VALIDATION COMPLETE")
        print("=" * 70 + "\n")


def main():
    result = find_scenario_batch()
    
    if result:
        batch, investments = result
        validate_scenario_batch(batch, investments)
    else:
        print("\nTo test this scenario, you need to:")
        print("1. Create a new batch")
        print("2. Add two investments:")
        print("   - Investor A: $30,000")
        print("   - Investor B: $10,000")
        print("3. Run valuation with 3% performance rate")
        print("4. Commit the valuation run")
        print("\nThen re-run this script to validate")


if __name__ == "__main__":
    main()
