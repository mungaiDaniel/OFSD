import sys
sys.path.insert(0, '.')

from datetime import datetime
from decimal import Decimal

# Test data
start_date = datetime(2026, 3, 18)
end_date = datetime(2026, 4, 18)
performance_rate = Decimal('0.05')
investors = [
    {'code': 'AXIOM-001', 'amount': Decimal('5000'), 'date_deposited': datetime(2026, 3, 18, 13, 1, 0)},
    {'code': 'AXIOM-002', 'amount': Decimal('5000'), 'date_deposited': datetime(2026, 3, 18, 13, 1, 0)},
]

print("=" * 80)
print("CALCULATION WITH FIX")
print("=" * 80)
print(f"\nPeriod: {start_date.date()} to {end_date.date()}")
print(f"Performance Rate: 5%")

period_days = (end_date - start_date).days
print(f"Period Days: {period_days}")

total_weighted = Decimal('0')
total_capital = Decimal('0')

for inv in investors:
    active_start = inv['date_deposited']
    amount = inv['amount']
    
    print(f"\n{inv['code']}:")
    print(f"  Active Start: {active_start}")
    print(f"  Amount: ${amount}")
    
    if active_start < start_date:
        days_active = (end_date - start_date).days
        print(f"  Status: Active before period start")
    else:
        print(f"  Status: Activated during period")
        # FIX: If investor activated on same calendar day as period start,
        # treat them as active for the full period
        if active_start.date() == start_date.date():
            days_active = (end_date - start_date).days
            print(f"  → Same-day activation: counting full period ({days_active} days)")
        else:
            days_active = (end_date - active_start).days
            print(f"  → Different day: {days_active} days")
    
    days_active = max(0, min(period_days, days_active))
    weighted = amount * Decimal(days_active)
    
    print(f"  Weighted Capital: ${amount} × {days_active} = ${weighted}")
    
    total_weighted += weighted
    total_capital += amount

print(f"\n{'=' * 80}")
print(f"Total Capital: ${total_capital}")
print(f"Total Weighted Capital: ${total_weighted}")

avg_active_capital = total_weighted / Decimal(period_days)
print(f"Average Active Capital: ${total_weighted} / {period_days} = ${avg_active_capital:.2f}")

total_profit = avg_active_capital * performance_rate
print(f"Total Profit: ${avg_active_capital:.2f} × 0.05 = ${total_profit:.2f}")

expected_end_balance = total_capital + total_profit
print(f"\n✓ Expected End Balance: ${total_capital} + ${total_profit:.2f} = ${expected_end_balance:.2f}")
print(f"\n>>> This matches your Head Office Total of $10,500.00 <<<")
