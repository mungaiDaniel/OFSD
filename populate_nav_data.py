#!/usr/bin/env python3
"""
Data Population Script for NAV Migration

Creates share classes for existing funds and backloads historical data.
Run after migrations are applied.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

def populate_data():
    try:
        from main import create_app
        from app.database.database import db
        from app.Batch.core_fund import CoreFund
        from app.Funds.share_class import ShareClass
        from app.Investments.model import Investment
        from app.Funds.investor_shares import InvestorShares
        from app.Funds.nav_history import NavHistory
        from decimal import Decimal
        from datetime import date

        app = create_app()
        with app.app_context():
            session = db.session

            print("=== DATA POPULATION FOR NAV MIGRATION ===")

            # 1. Create share classes for existing funds
            print("\n1. Creating share classes...")
            funds = session.query(CoreFund).filter(CoreFund.is_active == True).all()

            for fund in funds:
                # Check if share classes already exist
                existing_classes = session.query(ShareClass).filter(ShareClass.core_fund_id == fund.id).count()
                if existing_classes > 0:
                    print(f"  ✓ {fund.fund_name}: Already has {existing_classes} share classes")
                    continue

                # Create default KES and USD classes
                kes_class = ShareClass(
                    core_fund_id=fund.id,
                    class_name=f"{fund.fund_name} Class I - KES",
                    class_code=f"{fund.fund_code}_KES_I",
                    currency="KES",
                    is_active=True
                )
                usd_class = ShareClass(
                    core_fund_id=fund.id,
                    class_name=f"{fund.fund_name} Class I - USD",
                    class_code=f"{fund.fund_code}_USD_I",
                    currency="USD",
                    is_active=True
                )

                session.add(kes_class)
                session.add(usd_class)
                print(f"  ✓ {fund.fund_name}: Created KES and USD share classes")

            session.commit()

            # 2. Backload existing investments to share classes
            print("\n2. Backloading existing investments...")
            investments = session.query(Investment).filter(Investment.share_class_id.is_(None)).all()

            for inv in investments:
                # Find appropriate share class (prefer KES for now, can be updated later)
                share_class = session.query(ShareClass).filter(
                    ShareClass.core_fund_id == inv.fund_id,
                    ShareClass.currency == "KES"
                ).first()

                if share_class:
                    inv.share_class_id = share_class.id
                    inv.deposit_date = inv.date_deposited.date() if inv.date_deposited else None

                    # Create investor_shares record if shares_owned exists
                    if inv.shares_owned and inv.shares_owned > 0:
                        # Assume deployment NAV of 1000.00 for backloading (can be updated)
                        deployment_nav = Decimal("1000.00")
                        investor_share = InvestorShares(
                            investment_id=inv.id,
                            share_class_id=share_class.id,
                            batch_id=inv.batch_id,
                            shares_owned=inv.shares_owned,
                            deployment_nav=deployment_nav,
                            deployment_date=inv.deposit_date,
                            is_active=True
                        )
                        session.add(investor_share)

                    print(f"  ✓ Backloaded {inv.internal_client_code} to {share_class.class_code}")
                else:
                    print(f"  ⚠️ No share class found for investment {inv.id}")

            session.commit()

            # 3. Create sample NAV history (placeholder)
            print("\n3. Creating sample NAV history...")
            share_classes = session.query(ShareClass).all()

            for cls in share_classes:
                # Create a sample NAV record
                nav_record = NavHistory(
                    share_class_id=cls.id,
                    nav_date=date.today(),
                    nav_per_share=Decimal("1000.00"),
                    total_fund_nav=Decimal("1000000.00"),
                    source="valuation"
                )
                session.add(nav_record)
                print(f"  ✓ Created NAV history for {cls.class_code}")

            session.commit()

            print("\n=== DATA POPULATION COMPLETE ===")
            print("Share classes created, investments backloaded, NAV history initialized.")

    except Exception as e:
        print(f"Error during data population: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    populate_data()