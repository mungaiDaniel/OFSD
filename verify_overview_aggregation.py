#!/usr/bin/env python3
"""
Verify that the Overview stats endpoint correctly aggregates both Batch 1 and Batch 2 totals.
Expected: Batch 1 (Axiom+Atium committed) + Batch 2 (Axiom undeployed) = $519,071.61 AUM
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database.database import db
from app.Investments.model import Investment, EpochLedger
from app.Batch.model import Batch
from decimal import Decimal
from sqlalchemy import func


def verify_overview_aggregation():
    from main import app

    with app.app_context():
        print("\n" + "="*70)
        print("OVERVIEW STATS AGGREGATION VERIFICATION")
        print("="*70)

        # Fetch both batches
        batches = db.session.query(Batch).all()
        if not batches:
            print("❌ No batches found in database")
            return

        for batch in batches:
            print(f"\n🔍 Batch: {batch.batch_name}")
            print(f"   ID: {batch.id}, Certificate: {batch.certificate_number}")

            # Investments for this batch
            investments = db.session.query(Investment).filter_by(batch_id=batch.id).all()
            print(f"   Investments: {len(investments)}")

            batch_principal = Decimal("0")
            for inv in investments:
                batch_principal += Decimal(str(inv.amount_deposited or 0))
                print(f"     - {inv.investor_name} ({inv.internal_client_code}): ${float(inv.amount_deposited):,.2f} ({inv.fund_name})")

            print(f"   Total Principal: ${float(batch_principal):,.2f}")

            # Check for committed epochs
            ledger_rows = db.session.query(EpochLedger).filter(
                EpochLedger.internal_client_code.in_(
                    db.session.query(Investment.internal_client_code).filter_by(batch_id=batch.id)
                )
            ).order_by(EpochLedger.epoch_end.desc()).all()

            if ledger_rows:
                print(f"   Committed Epochs: {len(set(l.epoch_end for l in ledger_rows))}")
                latest_epoch_end = max(l.epoch_end for l in ledger_rows)
                print(f"   Latest Epoch End: {latest_epoch_end.date()}")

                # Sum latest balances by investor
                latest_ledgers_subq = db.session.query(
                    EpochLedger.internal_client_code,
                    func.max(EpochLedger.epoch_end).label("max_epoch")
                ).filter(
                    EpochLedger.internal_client_code.in_(
                        db.session.query(Investment.internal_client_code).filter_by(batch_id=batch.id)
                    )
                ).group_by(EpochLedger.internal_client_code).subquery()

                latest = db.session.query(
                    EpochLedger.internal_client_code,
                    EpochLedger.fund_name,
                    EpochLedger.end_balance,
                    EpochLedger.profit
                ).join(
                    latest_ledgers_subq,
                    (EpochLedger.internal_client_code == latest_ledgers_subq.c.internal_client_code) &
                    (EpochLedger.epoch_end == latest_ledgers_subq.c.max_epoch)
                ).all()

                batch_aum = Decimal("0")
                batch_profit = Decimal("0")
                for row in latest:
                    batch_aum += Decimal(str(row.end_balance or 0))
                    batch_profit += Decimal(str(row.profit or 0))
                    print(f"     - {row.internal_client_code} ({row.fund_name}): end_balance=${float(row.end_balance):,.2f} profit=${float(row.profit):,.2f}")

                print(f"   Batch AUM (committed): ${float(batch_aum):,.2f}")
                print(f"   Batch Profit: ${float(batch_profit):,.2f}")
            else:
                print(f"   ✓ Undeployed (no committed epochs)")

        # Now check what the endpoint calculates
        print("\n" + "-"*70)
        print("CALLING /api/v1/stats/overview ENDPOINT")
        print("-"*70)

        from flask.testing import FlaskClient
        client = app.test_client()

        # Get a token (you may need to set up auth differently in your environment)
        from tests.conftest import get_test_jwt_token
        token = get_test_jwt_token(client)

        response = client.get(
            '/api/v1/stats/overview',
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code == 200:
            data = response.get_json()["data"]
            print(f"\n✅ Total AUM: ${data['total_aum']:,.2f}")
            print(f"   Total Profit: ${data['total_profit']:,.2f}")
            print(f"   Performance: {data['performance_pct']:.2f}%")
            print(f"   Total Withdrawals: ${data['total_withdrawals']:,.2f}")
            print(f"   Total Investors: {data['total_investors']}")
            print(f"   Active Batches: {data['active_batches']}")

            # Expect: Batch 1 AUM $269,071.61 + Batch 2 AUM $250,000 = $519,071.61
            expected_aum = Decimal("519071.61")
            actual_aum = Decimal(str(data['total_aum']))
            
            if abs(actual_aum - expected_aum) < Decimal("1.00"):
                print(f"\n✅ AUM MATCHES EXPECTED: ${float(expected_aum):,.2f}")
            else:
                print(f"\n⚠️  AUM DIFFERS from expected ${float(expected_aum):,.2f}")
                print(f"   Difference: ${float(actual_aum - expected_aum):,.2f}")

            # Flow series for deposit visualization
            print(f"\n📊 Flow Series (Deposits/Withdrawals):")
            for point in data.get("flow_series", []):
                print(f"   {point['label']}: Deposits ${point['deposits']:,.2f}, Withdrawals ${point['withdrawals']:,.2f}")
        else:
            print(f"❌ API failed: {response.status_code}")
            print(response.get_json())


if __name__ == '__main__':
    verify_overview_aggregation()
