#!/usr/bin/env python3
"""
Debug script: Verify the corrected portfolio calculation for AXIOM-002
"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.Investments.model import EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES
    from sqlalchemy import func

    CLIENT = 'AXIOM-002'
    FUND = 'Axiom'

    print(f'\n=== CORRECTED PORTFOLIO CALC for {CLIENT} / {FUND} ===\n')

    # Latest epoch
    latest = db.session.query(EpochLedger).filter(
        EpochLedger.internal_client_code == CLIENT,
        func.lower(EpochLedger.fund_name) == FUND.lower()
    ).order_by(EpochLedger.epoch_end.desc()).first()

    if not latest:
        print('No epoch ledger found!')
        sys.exit(1)

    print(f'Latest Epoch:  {latest.epoch_start.date()} → {latest.epoch_end.date()}')
    print(f'Epoch End Bal: ${float(latest.end_balance):,.2f}')

    # 1. Total approved withdrawals
    total_approved = db.session.query(
        func.coalesce(func.sum(Withdrawal.amount), Decimal("0"))
    ).filter(
        Withdrawal.internal_client_code == CLIENT,
        func.lower(Withdrawal.fund_name) == FUND.lower(),
        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
    ).scalar() or Decimal("0")
    total_approved = Decimal(str(total_approved))

    # 2. Total captured in ALL epochs
    total_captured = db.session.query(
        func.coalesce(func.sum(EpochLedger.withdrawals), Decimal("0"))
    ).filter(
        EpochLedger.internal_client_code == CLIENT,
        func.lower(EpochLedger.fund_name) == FUND.lower(),
    ).scalar() or Decimal("0")
    total_captured = Decimal(str(total_captured))

    # 3. Uncaptured
    uncaptured = max(Decimal("0"), total_approved - total_captured)

    epoch_end_balance = Decimal(str(latest.end_balance))
    current_standing = epoch_end_balance - uncaptured

    print(f'\nWithdrawals:')
    print(f'  Total approved (all time): ${float(total_approved):,.2f}')
    print(f'  Total in epoch ledgers:    ${float(total_captured):,.2f}')
    print(f'  Uncaptured (not in ledger):${float(uncaptured):,.2f}')
    print(f'\nCalculation:')
    print(f'  ${float(epoch_end_balance):,.2f} (epoch end) - ${float(uncaptured):,.2f} (uncaptured) = ${float(current_standing):,.2f}')
    print(f'\n  Current Standing = ${float(current_standing):,.2f}')
    print(f'  Expected $51,139.60: {"✅ CORRECT" if abs(float(current_standing) - 51139.60) < 1.0 else f"❌ WRONG (diff={abs(float(current_standing) - 51139.60):.2f})"}')

    # Show all withdrawal records for context
    print(f'\nAll withdrawals for {CLIENT}/{FUND}:')
    wds = db.session.query(Withdrawal).filter(
        Withdrawal.internal_client_code == CLIENT,
        func.lower(Withdrawal.fund_name) == FUND.lower()
    ).all()
    for w in wds:
        print(f'  ${float(w.amount):,.2f} | {w.status} | date={w.date_withdrawn}')
