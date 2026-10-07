#!/usr/bin/env python3
"""
Check if withdrawals are captured in ledgers
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from main import create_app
from config import DevelopmentConfig
from app.database.database import db
from app.Investments.model import EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES
from decimal import Decimal
from sqlalchemy import func

app = create_app(DevelopmentConfig)

with app.app_context():
    print("=" * 80)
    print("CHECKING IF WITHDRAWALS ARE IN LEDGERS")
    print("=" * 80)
    
    # Get latest ledger per investor/fund
    latest_ledger_per_key_sq = (
        db.session.query(
            EpochLedger.internal_client_code.label("internal_client_code"),
            func.lower(EpochLedger.fund_name).label("fund_lower"),
            func.max(EpochLedger.epoch_end).label("latest_epoch_end"),
        )
        .group_by(EpochLedger.internal_client_code, func.lower(EpochLedger.fund_name))
        .subquery("latest_ledger_per_key")
    )
    
    from sqlalchemy import and_
    latest_rows = (
        db.session.query(
            EpochLedger.internal_client_code,
            EpochLedger.fund_name,
            EpochLedger.withdrawals,
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
    
    print("\nLatest ledgers - Withdrawals column:")
    total_ledger_withdrawals = Decimal("0")
    for row in latest_rows:
        wd_amt = Decimal(str(row.withdrawals or 0))
        total_ledger_withdrawals += wd_amt
        print(f"  {row.internal_client_code:15} Fund: {row.fund_name:20}  Withdrawals: ${float(wd_amt):>10.2f}  Epoch: {row.epoch_end}")
    
    print(f"\nTotal withdrawals in latest ledgers: ${float(total_ledger_withdrawals):>12.2f}")
    
    # Get all approved withdrawals
    all_withdrawals = db.session.query(
        Withdrawal.internal_client_code,
        func.sum(Withdrawal.amount).label('total_amount')
    ).filter(
        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
    ).group_by(
        Withdrawal.internal_client_code
    ).all()
    
    print("\nAll Approved/Processed/Completed/Executed Withdrawals:")
    total_approved_wd = Decimal("0")
    for wd in all_withdrawals:
        amt = Decimal(str(wd.total_amount or 0))
        total_approved_wd += amt
        print(f"  {wd.internal_client_code:15}  Amount: ${float(amt):>12.2f}")
    
    print(f"\nTotal approved withdrawals: ${float(total_approved_wd):>12.2f}")
    
    print("\n" + "=" * 80)
    print(f"Ledger withdrawals:   ${float(total_ledger_withdrawals):>12.2f}")
    print(f"Approved withdrawals: ${float(total_approved_wd):>12.2f}")
    uncaptured = total_approved_wd - total_ledger_withdrawals
    print(f"Uncaptured (need to subtract): ${float(uncaptured):>12.2f}")
    print("=" * 80)
