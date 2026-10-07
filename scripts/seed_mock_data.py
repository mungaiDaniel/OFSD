"""
Seed Mock Data for Local Development
Populates local PostgreSQL with realistic funds, share classes, batches,
investments, NAV history, investor shares, and valuation snapshots.
"""

from datetime import datetime, timezone, date
from decimal import Decimal
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import create_app, Config
from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Funds.nav_history import NavHistory
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger
from app.Funds.investor_shares import InvestorShares
from app.Valuation.valuation_snapshot import ValuationSnapshot


def seed_mock_data():
    app = create_app(Config)
    with app.app_context():
        print("Creating all tables if not present...")
        db.create_all()

        # 1. Clean existing mock data
        print("Cleaning old data...")
        db.session.query(ValuationSnapshot).delete()
        db.session.query(InvestorShares).delete()
        db.session.query(EpochLedger).delete()
        db.session.query(Investment).delete()
        db.session.query(Batch).delete()
        db.session.query(NavHistory).delete()
        db.session.query(ShareClass).delete()
        db.session.query(CoreFund).delete()
        db.session.commit()

        print("Seeding Core Funds...")
        axiom = CoreFund(fund_name="Axiom", fund_code="AXM", is_active=True)
        atium = CoreFund(fund_name="Atium", fund_code="ATM", is_active=True)
        db.session.add_all([axiom, atium])
        db.session.commit()

        print("Seeding Share Classes...")
        sc_axiom_usd = ShareClass(
            core_fund_id=axiom.id,
            class_name="Axiom USD Class A",
            class_code="AXM-USD-A",
            currency="USD",
            is_active=True,
            current_nav=Decimal("115.450000"),
        )
        sc_atium_kes = ShareClass(
            core_fund_id=atium.id,
            class_name="Atium KES Class I",
            class_code="ATM-KES-I",
            currency="KES",
            is_active=True,
            current_nav=Decimal("1389.573700"),
        )
        sc_atium_usd = ShareClass(
            core_fund_id=atium.id,
            class_name="Atium USD Class A",
            class_code="ATM-USD-A",
            currency="USD",
            is_active=True,
            current_nav=Decimal("108.250000"),
        )
        db.session.add_all([sc_axiom_usd, sc_atium_kes, sc_atium_usd])
        db.session.commit()

        print("Seeding NavHistory...")
        nav_entries = [
            # Axiom USD
            NavHistory(share_class_id=sc_axiom_usd.id, nav_date=date(2026, 1, 15), nav_per_share=Decimal("100.000000"), source="deployment"),
            NavHistory(share_class_id=sc_axiom_usd.id, nav_date=date(2026, 2, 15), nav_per_share=Decimal("105.200000"), source="valuation"),
            NavHistory(share_class_id=sc_axiom_usd.id, nav_date=date(2026, 3, 15), nav_per_share=Decimal("110.800000"), source="valuation"),
            NavHistory(share_class_id=sc_axiom_usd.id, nav_date=date(2026, 4, 15), nav_per_share=Decimal("115.450000"), source="valuation"),
            # Atium KES
            NavHistory(share_class_id=sc_atium_kes.id, nav_date=date(2026, 1, 10), nav_per_share=Decimal("1200.000000"), source="deployment"),
            NavHistory(share_class_id=sc_atium_kes.id, nav_date=date(2026, 2, 10), nav_per_share=Decimal("1260.500000"), source="valuation"),
            NavHistory(share_class_id=sc_atium_kes.id, nav_date=date(2026, 3, 10), nav_per_share=Decimal("1320.000000"), source="valuation"),
            NavHistory(share_class_id=sc_atium_kes.id, nav_date=date(2026, 4, 10), nav_per_share=Decimal("1389.573700"), source="valuation"),
            # Atium USD
            NavHistory(share_class_id=sc_atium_usd.id, nav_date=date(2026, 2, 1), nav_per_share=Decimal("100.000000"), source="deployment"),
            NavHistory(share_class_id=sc_atium_usd.id, nav_date=date(2026, 3, 1), nav_per_share=Decimal("104.500000"), source="valuation"),
            NavHistory(share_class_id=sc_atium_usd.id, nav_date=date(2026, 4, 1), nav_per_share=Decimal("108.250000"), source="valuation"),
        ]
        db.session.add_all(nav_entries)
        db.session.commit()

        print("Seeding Batches...")
        batch1 = Batch(
            batch_name="Batch Jan 2026 - Axiom",
            certificate_number="CERT-AXM-001",
            total_principal=Decimal("100000.00"),
            date_deployed=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            deployment_date_actual=date(2026, 1, 15),
            duration_days=365,
            is_active=True,
            is_transferred=True,
            deployment_confirmed=True,
            stage=4,
            share_class_id=sc_axiom_usd.id,
            total_shares=Decimal("1000.000000"),
            deployment_nav=Decimal("100.000000"),
            deployment_total_nav=Decimal("100000.00"),
        )
        batch2 = Batch(
            batch_name="Batch Jan 2026 - Atium KES",
            certificate_number="CERT-ATM-002",
            total_principal=Decimal("1000000.00"),
            date_deployed=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
            deployment_date_actual=date(2026, 1, 10),
            duration_days=365,
            is_active=True,
            is_transferred=True,
            deployment_confirmed=True,
            stage=4,
            share_class_id=sc_atium_kes.id,
            total_shares=Decimal("771.920000"),
            deployment_nav=Decimal("1200.000000"),
            deployment_total_nav=Decimal("926304.00"),
        )
        batch3 = Batch(
            batch_name="Batch Feb 2026 - Atium USD",
            certificate_number="CERT-ATM-003",
            total_principal=Decimal("50000.00"),
            date_deployed=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
            deployment_date_actual=date(2026, 2, 1),
            duration_days=365,
            is_active=True,
            is_transferred=True,
            deployment_confirmed=True,
            stage=4,
            share_class_id=sc_atium_usd.id,
            total_shares=Decimal("500.000000"),
            deployment_nav=Decimal("100.000000"),
            deployment_total_nav=Decimal("50000.00"),
        )
        db.session.add_all([batch1, batch2, batch3])
        db.session.commit()

        print("Seeding Investments...")
        inv1 = Investment(
            investor_name="Kamal Mani",
            investor_email="kamal.mani@example.com",
            investor_phone="+254711000001",
            internal_client_code="AXM-001",
            amount_deposited=Decimal("100000.00"),
            transfer_fee_deducted=Decimal("0.00"),
            deployment_fee_deducted=Decimal("0.00"),
            date_deposited=datetime(2026, 1, 5, 8, 30, tzinfo=timezone.utc),
            deposit_date=date(2026, 1, 5),
            fund_name="Axiom",
            fund_id=axiom.id,
            batch_id=batch1.id,
            share_class_id=sc_axiom_usd.id,
            shares_owned=Decimal("1000.0000"),
            currency_type="USD",
        )
        inv2 = Investment(
            investor_name="Joy Kendi Muthuri",
            investor_email="joy.kendi@example.com",
            investor_phone="+254711000002",
            internal_client_code="ATM-001",
            amount_deposited=Decimal("1000000.00"),
            transfer_fee_deducted=Decimal("500.00"),
            deployment_fee_deducted=Decimal("1500.00"),
            date_deposited=datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc),
            deposit_date=date(2026, 1, 2),
            fund_name="Atium",
            fund_id=atium.id,
            batch_id=batch2.id,
            share_class_id=sc_atium_kes.id,
            shares_owned=Decimal("771.9200"),
            share_series="Class I - KES",
            currency_type="KES",
        )
        inv3 = Investment(
            investor_name="Ann Wambui Kithinzi",
            investor_email="ann.kithinzi@example.com",
            investor_phone="+254711000003",
            internal_client_code="ATM-002",
            amount_deposited=Decimal("50000.00"),
            transfer_fee_deducted=Decimal("50.00"),
            deployment_fee_deducted=Decimal("150.00"),
            date_deposited=datetime(2026, 1, 25, 11, 0, tzinfo=timezone.utc),
            deposit_date=date(2026, 1, 25),
            fund_name="Atium",
            fund_id=atium.id,
            batch_id=batch3.id,
            share_class_id=sc_atium_usd.id,
            shares_owned=Decimal("498.0000"),
            currency_type="USD",
        )
        db.session.add_all([inv1, inv2, inv3])
        db.session.commit()

        print("Seeding InvestorShares...")
        ish1 = InvestorShares(
            investment_id=inv1.id,
            share_class_id=sc_axiom_usd.id,
            batch_id=batch1.id,
            shares_owned=Decimal("1000.000000"),
            deployment_nav=Decimal("100.000000"),
            deployment_date=date(2026, 1, 15),
            is_active=True,
        )
        ish2 = InvestorShares(
            investment_id=inv2.id,
            share_class_id=sc_atium_kes.id,
            batch_id=batch2.id,
            shares_owned=Decimal("771.920000"),
            deployment_nav=Decimal("1200.000000"),
            deployment_date=date(2026, 1, 10),
            is_active=True,
        )
        ish3 = InvestorShares(
            investment_id=inv3.id,
            share_class_id=sc_atium_usd.id,
            batch_id=batch3.id,
            shares_owned=Decimal("498.000000"),
            deployment_nav=Decimal("100.000000"),
            deployment_date=date(2026, 2, 1),
            is_active=True,
        )
        db.session.add_all([ish1, ish2, ish3])
        db.session.commit()

        print("Seeding ValuationSnapshots (Historical Valuations)...")
        # Snapshots for Kamal Mani (inv1)
        snaps_inv1 = [
            ValuationSnapshot(
                investor_shares_id=ish1.id,
                valuation_date=date(2026, 2, 15),
                nav_per_share=Decimal("105.200000"),
                shares_held=Decimal("1000.000000"),
                market_value=Decimal("105200.00"),
                performance_pct=Decimal("5.2000"),
            ),
            ValuationSnapshot(
                investor_shares_id=ish1.id,
                valuation_date=date(2026, 3, 15),
                nav_per_share=Decimal("110.800000"),
                shares_held=Decimal("1000.000000"),
                market_value=Decimal("110800.00"),
                performance_pct=Decimal("10.8000"),
            ),
            ValuationSnapshot(
                investor_shares_id=ish1.id,
                valuation_date=date(2026, 4, 15),
                nav_per_share=Decimal("115.450000"),
                shares_held=Decimal("1000.000000"),
                market_value=Decimal("115450.00"),  # <- Authoritative current balance (not 100,000!)
                performance_pct=Decimal("15.4500"),
            ),
        ]

        # Snapshots for Joy Kendi Muthuri (inv2)
        snaps_inv2 = [
            ValuationSnapshot(
                investor_shares_id=ish2.id,
                valuation_date=date(2026, 2, 10),
                nav_per_share=Decimal("1260.500000"),
                shares_held=Decimal("771.920000"),
                market_value=Decimal("973005.16"),
                performance_pct=Decimal("5.0417"),
            ),
            ValuationSnapshot(
                investor_shares_id=ish2.id,
                valuation_date=date(2026, 3, 10),
                nav_per_share=Decimal("1320.000000"),
                shares_held=Decimal("771.920000"),
                market_value=Decimal("1018934.40"),
                performance_pct=Decimal("10.0000"),
            ),
            ValuationSnapshot(
                investor_shares_id=ish2.id,
                valuation_date=date(2026, 4, 10),
                nav_per_share=Decimal("1389.573700"),
                shares_held=Decimal("771.920000"),
                market_value=Decimal("1072639.73"),  # <- Authoritative current balance (not 998,000!)
                performance_pct=Decimal("15.7978"),
            ),
        ]

        # Snapshots for Ann Wambui Kithinzi (inv3)
        snaps_inv3 = [
            ValuationSnapshot(
                investor_shares_id=ish3.id,
                valuation_date=date(2026, 3, 1),
                nav_per_share=Decimal("104.500000"),
                shares_held=Decimal("498.000000"),
                market_value=Decimal("52041.00"),
                performance_pct=Decimal("4.5000"),
            ),
            ValuationSnapshot(
                investor_shares_id=ish3.id,
                valuation_date=date(2026, 4, 1),
                nav_per_share=Decimal("108.250000"),
                shares_held=Decimal("498.000000"),
                market_value=Decimal("53908.50"),  # <- Authoritative current balance (not 49,800!)
                performance_pct=Decimal("8.2500"),
            ),
        ]

        db.session.add_all(snaps_inv1 + snaps_inv2 + snaps_inv3)
        db.session.commit()

        print("\n=== Mock Data Successfully Seeded! ===")
        print(f"CoreFunds: {db.session.query(CoreFund).count()}")
        print(f"ShareClasses: {db.session.query(ShareClass).count()}")
        print(f"NavHistory: {db.session.query(NavHistory).count()}")
        print(f"Batches: {db.session.query(Batch).count()}")
        print(f"Investments: {db.session.query(Investment).count()}")
        print(f"InvestorShares: {db.session.query(InvestorShares).count()}")
        print(f"ValuationSnapshots: {db.session.query(ValuationSnapshot).count()}")


if __name__ == "__main__":
    seed_mock_data()
