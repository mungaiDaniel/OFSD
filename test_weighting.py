from decimal import Decimal
base = Decimal('320651.18')
deps = Decimal('120000.00')

for denom in [30, 31]:
    for days_active in [20, 21, 22]:
        weighted_deps = deps * Decimal(days_active) / Decimal(denom)
        weighted_cap = base + weighted_deps
        profit = weighted_cap * Decimal('0.0410')
        end_bal = base + deps + profit
        print(f"days={days_active}, den={denom} => Profit: {profit.quantize(Decimal('0.01'))}, EndBal: {end_bal.quantize(Decimal('0.01'))}")
