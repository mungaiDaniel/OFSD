"""
Debug script to test weighted capital calculation directly
"""
import sys
sys.path.insert(0, '.')

from app.database.database import db
from main import create_app
from config import DevelopmentConfig as Config
from app.Investments.model import Investment
from app.Batch.core_fund import CoreFund
from datetime import datetime
from decimal import Decimal

app = create_app(Config)

with app.app_context():
    print("=" * 100)
    print("WEIGHTED CAPITAL CALCULATION DEBUG")
    print("=" * 100)
    
    # Date range from the UI
    start_date = datetime(2026, 3, 19)  # As shown in screenshot
    end_date = datetime(2026, 4, 19)
    fund_name = "Axiom"
    
    print(f"\nPeriod: {start_date.date()} to {end_date.date()}")
    print(f"Fund: {fund_name}")
    
    # Get the fund
    core_fund = db.session.query(CoreFund).filter(
        CoreFund.fund_name.ilike(fund_name)
    ).first()
    
    if not core_fund:
        print(f"❌ Fund not found: {fund_name}")
        sys.exit(1)
    
    print(f"✓ Found fund: {core_fund.fund_name} (id={core_fund.id})")
    
    # Query investments like the service does
    investments = db.session.query(Investment).filter(
        (Investment.fund_id == core_fund.id) |
        ((Investment.fund_id == None) & (Investment.fund_name.ilike(fund_name)))
    ).all()
    
    print(f"\n[QUERY] Looking for investments where:")
    print(f"       fund_id == {core_fund.id} OR (fund_id IS NULL AND fund_name ILIKE '{fund_name}')")
    print(f"✓ Found {len(investments)} investments")
    
    if len(investments) == 0:
        print("❌ NO INVESTMENTS FOUND! This is why weighted capital is zero.")
        sys.exit(1)
    
    period_days = (end_date - start_date).days
    print(f"\nPeriod days: {period_days}")
    
    per_code = {}
    for inv in investments:
        print(f"\n--- Investment ---")
        print(f"Investor Code: {inv.internal_client_code}")
        print(f"Amount: ${inv.amount_deposited}")
        print(f"Date Deposited: {inv.date_deposited}")
        print(f"Date Transferred: {inv.date_transferred}")
        print(f"Fund ID: {inv.fund_id}")
        print(f"Fund Name: {inv.fund_name}")
        
        active_start = inv.date_transferred or inv.date_deposited
        print(f"Active Start: {active_start}")
        
        if active_start is None:
            print("⚠️  No active_start date - SKIPPING")
            continue
            
        if active_start >= end_date:
            print(f"⚠️  active_start ({active_start}) >= end_date ({end_date}) - SKIPPING")
            continue
        
        code = inv.internal_client_code
        amount = Decimal(str(inv.amount_deposited))
        
        if code not in per_code:
            per_code[code] = {
                "principal_before_start": Decimal("0"),
                "deposits_during_period": Decimal("0"),
                "weighted_capital": Decimal("0"),
            }
        
        # Calculate days active
        if active_start < start_date:
            print(f"📍 Status: PRINCIPAL BEFORE START (activated {active_start.date()} < {start_date.date()})")
            per_code[code]["principal_before_start"] += amount
            days_active = (end_date - start_date).days
        else:
            print(f"📍 Status: DEPOSIT DURING PERIOD")
            per_code[code]["deposits_during_period"] += amount
            if active_start.date() == start_date.date():
                days_active = (end_date - start_date).days
                print(f"   Same-day activation: full period ({days_active} days)")
            else:
                days_active = (end_date - active_start).days
                print(f"   Activated during period: {days_active} days")
        
        days_active = max(0, min(period_days, days_active))
        print(f"Final days_active: {days_active}")
        
        weighted = amount * Decimal(days_active)
        per_code[code]["weighted_capital"] += weighted
        print(f"Weighted capital: ${amount} × {days_active} = ${weighted}")
    
    print(f"\n{'=' * 100}")
    print("FINAL RESULTS")
    print(f"{'=' * 100}")
    
    total_weighted = Decimal("0")
    total_principal_before = Decimal("0")
    total_deposits_during = Decimal("0")
    
    for code, agg in per_code.items():
        print(f"\n{code}:")
        print(f"  Principal Before Start: ${agg['principal_before_start']}")
        print(f"  Deposits During Period: ${agg['deposits_during_period']}")
        print(f"  Weighted Capital: ${agg['weighted_capital']}")
        
        total_weighted += agg["weighted_capital"]
        total_principal_before += agg["principal_before_start"]
        total_deposits_during += agg["deposits_during_period"]
    
    print(f"\n{'=' * 100}")
    print(f"Total Principal Before: ${total_principal_before}")
    print(f"Total Deposits During: ${total_deposits_during}")
    print(f"TOTAL WEIGHTED CAPITAL: ${total_weighted}")
    
    if total_weighted <= 0:
        print("\n❌ WEIGHTED CAPITAL IS ZERO - This will cause 'cannot allocate profit' error")
    else:
        print("\n✓ Weighted capital is positive - calculation should work")
        
        period_days = (end_date - start_date).days
        avg_active_capital = total_weighted / Decimal(period_days)
        performance_rate = Decimal("0.05")
        total_profit = avg_active_capital * performance_rate
        
        print(f"\nAverage Active Capital: ${total_weighted} / {period_days} = ${avg_active_capital:.2f}")
        print(f"Total Profit (5%): ${avg_active_capital:.2f} × 0.05 = ${total_profit:.2f}")
        print(f"Expected End Balance: ${total_principal_before + total_deposits_during + total_profit:.2f}")
