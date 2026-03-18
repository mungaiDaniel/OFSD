import sys
sys.path.insert(0, '.')

from app.database.database import db
from main import create_app
from config import DevelopmentConfig as Config
from app.Investments.model import Investment
from datetime import datetime
from decimal import Decimal

app = create_app(Config)
print("App created successfully")
try:
    with app.app_context():
    # Get all Axiom investments
    investments = db.session.query(Investment).filter(
        (Investment.fund_name == 'Axiom') | (Investment.fund_id == 1)
    ).all()
    
    print("=" * 80)
    print("AXIOM INVESTMENTS")
    print("=" * 80)
    for inv in investments:
        print(f"\nInvestor: {inv.internal_client_code}")
        print(f"  Amount: ${inv.amount_deposited}")
        print(f"  Date Deposited: {inv.date_deposited}")
        print(f"  Date Transferred: {inv.date_transferred}")
        print(f"  Fund ID: {inv.fund_id}")
        print(f"  Fund Name: {inv.fund_name}")
    
    print("\n" + "=" * 80)
    print(f"Total Axiom investments: {len(investments)}")
    
    # Now simulate the calculation
    print("\n" + "=" * 80)
    print("CALCULATION SIMULATION")
    print("=" * 80)
    
    start_date = datetime(2026, 3, 18)
    end_date = datetime(2026, 4, 18)
    performance_rate = 0.05
    
    print(f"\nPeriod: {start_date.date()} to {end_date.date()}")
    print(f"Performance Rate: {performance_rate * 100}%")
    
    period_days = (end_date - start_date).days
    print(f"Period Days: {period_days}")
    
    total_weighted = 0
    total_capital = 0
    
    for inv in investments:
        active_start = inv.date_transferred or inv.date_deposited
        print(f"\n{inv.internal_client_code}:")
        print(f"  Active Start: {active_start}")
        print(f"  Amount: ${inv.amount_deposited}")
        
        if active_start < start_date:
            days_active = (end_date - start_date).days
            print(f"  Status: Active before period start")
        else:
            print(f"  Status: Activated during period")
            # FIX: If investor activated on same calendar day as period start,
            # treat them as active for the full period
            if active_start.date() == start_date.date():
                days_active = (end_date - start_date).days
                print(f"  Same-day activation: counting full period")
            else:
                days_active = (end_date - active_start).days
        
        days_active = max(0, min(period_days, days_active))
        print(f"  Days Active: {days_active}")
        
        weighted = inv.amount_deposited * days_active
        print(f"  Weighted Capital: ${inv.amount_deposited} × {days_active} = {weighted}")
        
        total_weighted += weighted
        total_capital += inv.amount_deposited
    
    print(f"\n{'=' * 80}")
    print(f"Total Capital: ${total_capital}")
    print(f"Total Weighted Capital: {total_weighted}")
    
    avg_active_capital = total_weighted / period_days
    print(f"Average Active Capital: {total_weighted} / {period_days} = ${avg_active_capital:.2f}")
    
    total_profit = avg_active_capital * Decimal(str(performance_rate))
    print(f"Total Profit: ${avg_active_capital:.2f} × {performance_rate} = ${total_profit:.2f}")
    
    expected_end_balance = total_capital + total_profit
    print(f"\nExpected End Balance: ${total_capital} + ${total_profit:.2f} = ${expected_end_balance:.2f}")
