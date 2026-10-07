#!/usr/bin/env python
"""
NAV-Based Valuation Service - Example Usage

This script demonstrates how to:
1. Set up share classes
2. Load investor share holdings
3. Execute a NAV-based valuation
4. Query valuation results
"""

from datetime import date
from decimal import Decimal

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds import ShareClass, InvestorShares, NavHistory
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.logic.valuation_service import PortfolioValuationService, NavInput


def example_setup_share_classes():
    """
    Step 1: Create share classes for each fund.
    
    In production, this is done once during fund setup.
    """
    print("\n=== Step 1: Setting up Share Classes ===")
    
    # Get or create a fund
    axiom = CoreFund.query.filter_by(fund_name="Axiom").first()
    if not axiom:
        axiom = CoreFund(fund_name="Axiom", fund_code="AXIOM", is_active=True)
        db.session.add(axiom)
        db.session.commit()
    
    # Create share classes
    share_classes = [
        {
            "name": "Class I - KES",
            "code": "AxiomI-KES",
            "currency": "KES",
        },
        {
            "name": "Class I - USD",
            "code": "AxiomI-USD",
            "currency": "USD",
        },
    ]
    
    for sc_data in share_classes:
        existing = ShareClass.query.filter(
            ShareClass.core_fund_id == axiom.id,
            ShareClass.class_code == sc_data["code"],
        ).first()
        
        if not existing:
            sc = ShareClass(
                core_fund_id=axiom.id,
                class_name=sc_data["name"],
                class_code=sc_data["code"],
                currency=sc_data["currency"],
                is_active=True,
            )
            db.session.add(sc)
            print(f"Created: {sc.class_name}")
    
    db.session.commit()


def example_create_investor_shares():
    """
    Step 2: Create investor_shares records (normally from Add Investor form).
    
    Each record represents an investor's holding in a share class.
    """
    print("\n=== Step 2: Creating Investor Share Holdings ===")
    
    # Get share class and batch
    share_class = ShareClass.query.filter_by(class_code="AxiomI-KES").first()
    batch = Batch.query.first()
    
    if not batch:
        print("ERROR: No batch found. Create a batch first.")
        return
    
    # Get an investment
    investment = Investment.query.first()
    if not investment:
        print("ERROR: No investment found. Create an investment first.")
        return
    
    # Check if investor_shares already exists
    existing = InvestorShares.query.filter(
        InvestorShares.investment_id == investment.id,
        InvestorShares.share_class_id == share_class.id,
    ).first()
    
    if not existing:
        inv_shares = InvestorShares(
            investment_id=investment.id,
            share_class_id=share_class.id,
            batch_id=batch.id,
            shares_owned=Decimal("771.92"),
            deployment_nav=Decimal("1330.00"),
            deployment_date=date(2026, 3, 15),
            is_active=True,
        )
        db.session.add(inv_shares)
        db.session.commit()
        print(f"Created: {inv_shares}")


def example_execute_valuation():
    """
    Step 3: Execute a NAV-based valuation.
    
    This creates valuation snapshots and nav_history records.
    """
    print("\n=== Step 3: Executing NAV Valuation ===")
    
    # Prepare NAV inputs (from external source, e.g., Mauritius HQ)
    nav_inputs = [
        NavInput(
            share_class_id=1,
            nav_per_share=Decimal("1389.5737"),
            total_fund_nav=Decimal("1072636.69"),
        ),
    ]
    
    # Execute valuation
    try:
        results = PortfolioValuationService.execute_valuation(
            valuation_date=date(2026, 4, 10),
            nav_inputs=nav_inputs,
            dry_run=False,  # Set to True to validate without persisting
        )
        
        for result in results:
            print(f"\nValuation Results for Class {result.share_class_id}:")
            print(f"  Valuation Date: {result.valuation_date}")
            print(f"  NAV Per Share: ${result.nav_per_share}")
            print(f"  Total Fund NAV: ${result.total_fund_nav}")
            print(f"  System Total: ${result.system_total}")
            print(f"  Reconciliation Diff: ${result.reconciliation_diff}")
            print(f"  Snapshots Created: {result.snapshots_created}")
            print(f"  NAV History Created: {result.nav_history_created}")
    
    except ValueError as e:
        print(f"ERROR: {str(e)}")


def example_query_portfolio_value():
    """
    Step 4: Query current portfolio value for a share class.
    """
    print("\n=== Step 4: Getting Current Portfolio Value ===")
    
    portfolio = PortfolioValuationService.get_current_portfolio_value(share_class_id=1)
    
    if "error" in portfolio:
        print(f"ERROR: {portfolio['error']}")
    else:
        print(f"Share Class {portfolio['share_class_id']}:")
        print(f"  Total Shares: {portfolio['total_shares']}")
        print(f"  Latest NAV: ${portfolio['latest_nav']} (as of {portfolio['nav_date']})")
        print(f"  Total Market Value: ${portfolio['total_market_value']}")


def example_query_investor_valuation():
    """
    Step 5: Query individual investor valuation.
    """
    print("\n=== Step 5: Getting Individual Investor Valuation ===")
    
    # Get an investor_shares record
    inv_shares = InvestorShares.query.first()
    if not inv_shares:
        print("ERROR: No investor_shares found.")
        return
    
    investor_val = PortfolioValuationService.get_investor_valuation(
        investor_shares_id=inv_shares.id
    )
    
    if "error" in investor_val:
        print(f"ERROR: {investor_val['error']}")
    else:
        print(f"Investor Shares {investor_val['investor_shares_id']}:")
        print(f"  Shares Held: {investor_val['shares_held']}")
        print(f"  Deployment NAV: ${investor_val['deployment_nav']}")
        print(f"  Current NAV: ${investor_val['current_nav']}")
        print(f"  Market Value: ${investor_val['market_value']}")
        print(f"  Cost Basis: ${investor_val['cost_basis']}")
        print(f"  Gain/Loss: ${investor_val['gain_loss']}")
        print(f"  Performance: {investor_val['performance_pct']}%")


def main():
    """Run all example steps."""
    print("=" * 60)
    print("NAV-Based Valuation Service - Example Usage")
    print("=" * 60)
    
    try:
        # Step 1: Set up share classes
        example_setup_share_classes()
        
        # Step 2: Create investor share holdings
        example_create_investor_shares()
        
        # Step 3: Execute valuation (dry-run for safety)
        print("\n--- DRY RUN (validation only) ---")
        nav_inputs = [
            NavInput(
                share_class_id=1,
                nav_per_share=Decimal("1389.5737"),
                total_fund_nav=Decimal("1072636.69"),
            ),
        ]
        
        results = PortfolioValuationService.execute_valuation(
            valuation_date=date(2026, 4, 10),
            nav_inputs=nav_inputs,
            dry_run=True,  # Don't persist
        )
        
        print(f"Dry run validation passed. Would create {results[0].snapshots_created} snapshots.")
        
        # Step 4 & 5: Query results (if data exists)
        example_query_portfolio_value()
        example_query_investor_valuation()
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)
    
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
