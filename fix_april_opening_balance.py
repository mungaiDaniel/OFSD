#!/usr/bin/env python3
"""
Fix April EpochLedger records to have correct start_balance values.

For fresh-start (April), each investor's row should have their individual opening balance,
not 0. This script updates the database records.
"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
from datetime import datetime, timezone
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    from app.database.database import db
    from app.Investments.model import EpochLedger, Investment
    from sqlalchemy import func

    # Define April period
    april_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    april_end = datetime(2026, 4, 30, tzinfo=timezone.utc)

    print("=" * 80)
    print("FIXING APRIL OPENING BALANCES")
    print("=" * 80)
    print()

    # Get all April EpochLedger records
    april_records = (
        db.session.query(EpochLedger)
        .filter(EpochLedger.epoch_start == april_start)
        .filter(EpochLedger.epoch_end == april_end)
        .order_by(EpochLedger.fund_name.asc(), EpochLedger.internal_client_code.asc())
        .all()
    )

    if not april_records:
        print("No April records found!")
        sys.exit(0)

    print(f"Found {len(april_records)} April records to update:")
    print()

    # Group by fund to calculate individual opening balances
    fund_totals = {}
    for record in april_records:
        fund = record.fund_name.lower()
        if fund not in fund_totals:
            fund_totals[fund] = {"count": 0, "current_start": Decimal("0"), "current_deposits": Decimal("0")}
        fund_totals[fund]["count"] += 1
        fund_totals[fund]["current_start"] += Decimal(str(record.start_balance or 0))
        fund_totals[fund]["current_deposits"] += Decimal(str(record.deposits or 0))

    # Calculate totals
    axiom_total_principal = Decimal("150000.00")
    atium_total_principal = Decimal("100000.00")

    updates = []
    for record in april_records:
        fund = record.fund_name.lower()
        code = record.internal_client_code

        if fund == "axiom":
            # Split $150,000 among 3 investors = $50,000 each
            new_start_balance = axiom_total_principal / Decimal("3")
            new_deposits = Decimal("0.00")
        elif fund == "atium":
            # Split $100,000 among 2 investors = $50,000 each
            new_start_balance = atium_total_principal / Decimal("2")
            new_deposits = Decimal("0.00")
        else:
            print(f"⚠️  Unknown fund: {fund}")
            continue

        old_start = record.start_balance
        old_deposits = record.deposits

        # Calculate new end balance
        old_profit = Decimal(str(record.profit or 0))
        old_withdrawals = Decimal(str(record.withdrawals or 0))
        new_end_balance = new_start_balance + new_deposits - old_withdrawals + old_profit

        print(f"{fund.upper()} - {code}:")
        print(f"  Start Balance:  ${old_start} → ${new_start_balance}")
        print(f"  Deposits:       ${old_deposits} → ${new_deposits}")
        print(f"  Withdrawals:    ${record.withdrawals}")
        print(f"  Profit:         ${record.profit}")
        print(f"  End Balance:    ${record.end_balance} → ${new_end_balance}")
        print()

        updates.append({
            "record": record,
            "new_start_balance": new_start_balance,
            "new_deposits": new_deposits,
            "new_end_balance": new_end_balance,
        })

    # Apply updates
    print(f"Applying {len(updates)} updates...")
    print()

    for update in updates:
        record = update["record"]
        record.start_balance = update["new_start_balance"]
        record.deposits = update["new_deposits"]
        record.end_balance = update["new_end_balance"]

    db.session.commit()

    print("✅ All April records updated successfully!")
    print()

    # Verify
    print("VERIFICATION:")
    print("=" * 80)
    axiom_sum = db.session.query(func.sum(EpochLedger.start_balance)).filter(
        EpochLedger.epoch_start == april_start,
        EpochLedger.epoch_end == april_end,
        func.lower(EpochLedger.fund_name) == "axiom",
    ).scalar() or Decimal("0")

    atium_sum = db.session.query(func.sum(EpochLedger.start_balance)).filter(
        EpochLedger.epoch_start == april_start,
        EpochLedger.epoch_end == april_end,
        func.lower(EpochLedger.fund_name) == "atium",
    ).scalar() or Decimal("0")

    print(f"Axiom April Opening Total:  ${axiom_sum} (expected: $150,000.00)")
    print(f"Atium April Opening Total:  ${atium_sum} (expected: $100,000.00)")
    print()

    if axiom_sum == axiom_total_principal and atium_sum == atium_total_principal:
        print("✅ Verification passed!")
    else:
        print("⚠️  Verification mismatch!")

    print("=" * 80)
