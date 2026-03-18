#!/usr/bin/env python3
"""
Data Integrity Verification Script
Checks fund mappings for Q1-2026-Axiom-Atium-Master batch
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import db
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Valuation.model import ValuationRun
from sqlalchemy import func

def verify_fund_mappings():
    """Verify that investors are properly mapped to funds"""

    print("🔍 Data Integrity Verification for Q1-2026-Axiom-Atium-Master")
    print("=" * 60)

    # Find the batch
    batch = db.session.query(Batch).filter(
        Batch.batch_name == 'Q1-2026-Axiom-Atium-Master'
    ).first()

    if not batch:
        print("❌ Batch 'Q1-2026-Axiom-Atium-Master' not found!")
        return

    print(f"✅ Found batch: {batch.batch_name} (ID: {batch.id})")

    # Get all investments in this batch
    investments = db.session.query(Investment).filter(
        Investment.batch_id == batch.id
    ).all()

    print(f"📊 Total investments in batch: {len(investments)}")

    # Check fund mappings
    fund_counts = {}
    axiom_investments = []
    atium_investments = []

    for inv in investments:
        fund_name = "Unknown"
        if inv.fund:
            fund_name = inv.fund.fund_name
        elif inv.fund_name:
            fund_name = inv.fund_name

        fund_counts[fund_name] = fund_counts.get(fund_name, 0) + 1

        if fund_name.lower() == 'axiom':
            axiom_investments.append(inv)
        elif fund_name.lower() == 'atium':
            atium_investments.append(inv)

    print("\n🏦 Fund Distribution:")
    for fund, count in fund_counts.items():
        print(f"  {fund}: {count} investors")

    print(f"\n🎯 Axiom-specific analysis:")
    print(f"  Axiom investors: {len(axiom_investments)}")

    if axiom_investments:
        print("  Sample Axiom investors:")
        for inv in axiom_investments[:3]:  # Show first 3
            print(f"    - {inv.investor_name} ({inv.internal_client_code}) - ${inv.amount_deposited}")

    # Check for committed valuations
    print("\n📈 Committed Valuations:")
    valuations = db.session.query(ValuationRun).filter(
        ValuationRun.status == 'Committed'
    ).all()

    axiom_valuations = []
    atium_valuations = []

    for v in valuations:
        # Get the fund name for this valuation
        fund = db.session.query(CoreFund).filter(CoreFund.id == v.core_fund_id).first()
        if fund:
            if fund.fund_name.lower() == 'axiom':
                axiom_valuations.append(v)
            elif fund.fund_name.lower() == 'atium':
                atium_valuations.append(v)

    print(f"  Axiom valuations: {len(axiom_valuations)}")
    print(f"  Atium valuations: {len(atium_valuations)}")

    if axiom_valuations:
        latest = max(axiom_valuations, key=lambda v: v.epoch_end)
        print(f"  Latest Axiom valuation: {latest.epoch_end.date()} - {latest.performance_rate * 100:.2f}%")

    # Check core_funds table
    print("\n🏛️  Core Funds Table:")
    core_funds = db.session.query(CoreFund).all()
    for fund in core_funds:
        print(f"  {fund.fund_name} (ID: {fund.id}) - Active: {fund.is_active}")

    print("\n" + "=" * 60)
    print("✅ Verification complete!")

if __name__ == "__main__":
    from main import create_app
    from config import DevelopmentConfig
    app = create_app(DevelopmentConfig)
    with app.app_context():
        verify_fund_mappings()