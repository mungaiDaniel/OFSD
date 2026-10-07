#!/usr/bin/env python3
"""
Quick check of what AUM should be - using Flask app context
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from main import create_app
from config import DevelopmentConfig
from app.database.database import db
from app.Investments.model import EpochLedger, Withdrawal, Investment, FINAL_WITHDRAWAL_STATUSES
from app.Batch.core_fund import CoreFund
from decimal import Decimal
from sqlalchemy import func, and_

app = create_app(DevelopmentConfig)

with app.app_context():
    print("=" * 80)
    print("CHECKING AUM CALCULATION")
    print("=" * 80)

    # Get all investments
    all_investments = db.session.query(
        Investment.internal_client_code,
        Investment.batch_id,
        Investment.fund_name,
        func.sum(Investment.amount_deposited).label('total_amount')
    ).group_by(
        Investment.internal_client_code,
        Investment.batch_id,
        Investment.fund_name
    ).all()

    print("\n1. All Investments (grouped by investor, batch, fund):")
    total_investments_all = Decimal("0")
    for inv in all_investments:
        amt = Decimal(str(inv.total_amount or 0))
        total_investments_all += amt
        print(f"  {inv.internal_client_code:15} Batch {inv.batch_id}  Fund: {inv.fund_name:20}  Amount: ${float(amt):>12.2f}")

    print(f"\nTotal of all investments (raw): ${float(total_investments_all):>12.2f}")

    # Get all withdrawals
    all_withdrawals = db.session.query(
        Withdrawal.internal_client_code,
        func.sum(Withdrawal.amount).label('total_amount')
    ).filter(
        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
    ).group_by(
        Withdrawal.internal_client_code
    ).all()

    print("\n2. All Final Withdrawals (by investor):")
    total_withdrawals_all = Decimal("0")
    for wd in all_withdrawals:
        amt = Decimal(str(wd.total_amount or 0))
        total_withdrawals_all += amt
        print(f"  {wd.internal_client_code:15}  Amount: ${float(amt):>12.2f}")

    print(f"\nTotal withdrawals: ${float(total_withdrawals_all):>12.2f}")

    # Get latest ledgers for understanding how system currently calculates
    latest_ledger_rows = db.session.query(EpochLedger).all()

    print("\n3. All Ledger entries:")
    total_ledger_aum = Decimal("0")
    for row in latest_ledger_rows:
        total_ledger_aum += Decimal(str(row.end_balance or 0))
        print(f"  {row.internal_client_code:15} Fund: {row.fund_name:20}  End Balance: ${float(Decimal(str(row.end_balance))):>12.2f}  Profit: ${float(Decimal(str(row.profit))):>10.2f}")

    print(f"\nTotal from all ledgers: ${float(total_ledger_aum):>12.2f}")

    # Calculate what it SHOULD be
    expected_aum = total_investments_all - total_withdrawals_all
    print("\n" + "=" * 80)
    print(f"EXPECTED AUM (all investments - withdrawals): ${float(expected_aum):>12.2f}")
    print("=" * 80)

    # Now run the stats logic step by step to see where the error is
    print("\n4. Running stats endpoint logic step by step:")
    
    latest_ledger_per_key_sq = (
        db.session.query(
            EpochLedger.internal_client_code.label("internal_client_code"),
            func.lower(EpochLedger.fund_name).label("fund_lower"),
            func.max(EpochLedger.epoch_end).label("latest_epoch_end"),
        )
        .group_by(EpochLedger.internal_client_code, func.lower(EpochLedger.fund_name))
        .subquery("latest_ledger_per_key")
    )
    
    latest_rows = (
        db.session.query(
            EpochLedger.internal_client_code,
            EpochLedger.fund_name,
            EpochLedger.end_balance,
            EpochLedger.profit,
            EpochLedger.epoch_end,
        )
        .join(
            latest_ledger_per_key_sq,
            and_(
                EpochLedger.internal_client_code == latest_ledger_per_key_sq.c.internal_client_code,
                func.lower(EpochLedger.fund_name) == latest_ledger_per_key_sq.c.fund_lower,
                EpochLedger.epoch_end == latest_ledger_per_key_sq.c.latest_epoch_end,
            ),
        )
        .all()
    )

    print("\n  Latest ledger rows (from grouped query):")
    total_from_latest_ledgers = Decimal("0")
    for row in latest_rows:
        total_from_latest_ledgers += Decimal(str(row.end_balance or 0))
        print(f"    {row.internal_client_code:15} Fund: {row.fund_name:20}  End Balance: ${float(Decimal(str(row.end_balance))):>12.2f}  Profit: ${float(Decimal(str(row.profit))):>10.2f}")
    
    print(f"\n  Total from latest ledgers: ${float(total_from_latest_ledgers):>12.2f}")

    # Now check the investment totals per investor/fund across batches
    print("\n5. Checking investments per investor/fund across batches:")
    
    from app.Batch.model import Batch as BatchModel
    all_batches = db.session.query(BatchModel).all()
    
    all_investments_full = db.session.query(
        Investment.id,
        Investment.batch_id,
        Investment.internal_client_code,
        func.lower(func.coalesce(Investment.fund_name, CoreFund.fund_name, "unknown")).label("fund_lower"),
        func.coalesce(Investment.fund_name, CoreFund.fund_name, "unknown").label("fund_name"),
        Investment.amount_deposited
    ).outerjoin(CoreFund, Investment.fund_id == CoreFund.id).all()

    # Build principal sums per investor+fund+batch
    investor_fund_batch_principals = {}
    
    for inv in all_investments_full:
        key = (inv.internal_client_code, inv.fund_lower)
        batch_key = (key, inv.batch_id)
        if batch_key not in investor_fund_batch_principals:
            investor_fund_batch_principals[batch_key] = Decimal("0")
        investor_fund_batch_principals[batch_key] += Decimal(str(inv.amount_deposited or 0))

    print("\n  Investments by investor/fund/batch:")
    for batch_key, amt in sorted(investor_fund_batch_principals.items()):
        (inv_code, fund_lower), batch_id = batch_key
        print(f"    {inv_code:15} Fund: {fund_lower:20} Batch {batch_id}  Amount: ${float(amt):>12.2f}")

    # Now simulate what the endpoint does
    print("\n6. Simulating endpoint AUM calculation:")
    latest_rows_by_key = {(r.internal_client_code, r.fund_name.lower()): r for r in latest_rows}
    
    total_aum = Decimal("0")
    unique_investors = set()
    
    # Build approved withdrawals map
    approved_withdrawal_rows = db.session.query(
        Withdrawal.internal_client_code,
        func.lower(func.coalesce(Withdrawal.fund_name, CoreFund.fund_name, "unknown")).label("fund_lower"),
        func.coalesce(func.sum(Withdrawal.amount), 0).label("total_amount")
    ).outerjoin(CoreFund, Withdrawal.fund_id == CoreFund.id).filter(
        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
    ).group_by(
        Withdrawal.internal_client_code,
        func.lower(func.coalesce(Withdrawal.fund_name, CoreFund.fund_name, "unknown"))
    ).all()

    approved_wd_map = {
        (row.internal_client_code, row.fund_lower): Decimal(str(row.total_amount or 0))
        for row in approved_withdrawal_rows
    }

    print("\n  Processing each investor/fund combination:")
    processed_keys = set()
    
    for (inv_code, fund_lower) in sorted(set((i.internal_client_code, i.fund_lower) for i in all_investments_full)):
        key = (inv_code, fund_lower)
        unique_investors.add(inv_code)
        
        if key in latest_rows_by_key:
            # Has ledger - use it as-is, it already includes all batches!
            ledger = latest_rows_by_key[key]
            current_value = Decimal(str(ledger.end_balance or 0))
            source = "ledger (includes all batches)"
        else:
            # No ledger: sum all fresh principals
            current_value = Decimal("0")
            for batch_id in set(b.id for b in all_batches):
                batch_key = (key, batch_id)
                if batch_key in investor_fund_batch_principals:
                    current_value += investor_fund_batch_principals[batch_key]
            source = "fresh principles"
        
        withdrawals_for_key = approved_wd_map.get(key, Decimal("0"))
        extra_note = ""
        if withdrawals_for_key > 0:
            current_value -= withdrawals_for_key
            extra_note += f" - ${float(withdrawals_for_key):.2f} withdrawal"
        
        total_aum += current_value
        print(f"    {inv_code:15} {fund_lower:20} = ${float(current_value):>12.2f} ({source}){extra_note}")

    print(f"\n  CALCULATED AUM from endpoint logic: ${float(total_aum):>12.2f}")
    print(f"  Expected correct AUM: ${float(expected_aum):>12.2f}")
    print(f"  Difference: ${float(total_aum - expected_aum):>12.2f}")
