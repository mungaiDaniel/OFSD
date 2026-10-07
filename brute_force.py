from decimal import Decimal

base_capital = Decimal("320651.18")
new_deposit = Decimal("120000.00")
target_total = Decimal("458170.29")
rate = Decimal("0.0410")

print("Brute forcing to find weighting...")
found = False

for num in range(1, 40):
    for den in range(1, 40):
        if num > den: continue
        
        weighted_new = new_deposit * Decimal(num) / Decimal(den)
        total_weighted = base_capital + weighted_new
        profit = total_weighted * rate
        # round to 2 decimals
        total_profit = profit.quantize(Decimal("0.01"))
        calc_total = base_capital + new_deposit + total_profit
        
        if abs(calc_total - target_total) <= Decimal("0.01"):
            print(f"MATCH! num={num}, den={den} (weight={num/den})")
            print(f"Profit: {total_profit}")
            found = True

if not found:
    print("No perfect rational fraction weight matched.")
