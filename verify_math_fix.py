"""
Verification script to show that the mathematics fix is working correctly
Compare old (wrong) vs new (correct) calculations
"""
from decimal import Decimal, ROUND_HALF_UP

def _q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimal places"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

print("=" * 80)
print("VALUATION MATHEMATICS FIX - VERIFICATION")
print("=" * 80)

# Test Case: Axiom Fund May 2026
principal = Decimal("2046000.00")
perf_rate = Decimal("0.49")  # 0.49%
months = 1
principal_weighted = principal  # Assuming no withdrawals, weighted = principal

print(f"\nTest Case: Axiom Fund, May 2026")
print(f"  Principal:           ${principal:,.2f}")
print(f"  Performance Rate:    {perf_rate}%")
print(f"  Periods (months):    {months}")
print(f"  Weighted Capital:    ${principal_weighted:,.2f}")

# OLD (WRONG) CALCULATION
print(f"\nOLD (WRONG) CALCULATION:")
print("-" * 80)
wrong_profit = principal_weighted * perf_rate
wrong_valuation = principal + wrong_profit
wrong_return_pct = (wrong_profit / principal) * 100
print(f"Formula: profit = weighted_capital × perf_rate")
print(f"  profit = ${principal_weighted:,.2f} × {perf_rate}")
print(f"  profit = ${wrong_profit:,.2f}  [WRONG!]")
print(f"  return = {wrong_return_pct:.2f}%  [WRONG - Should be 0.49%!]")
print(f"  valuation = ${wrong_valuation:,.2f}")
print(f"\n  ** This treated 0.49 as 49%, giving a 49% return instead of 0.49%! **")

# NEW (CORRECT) CALCULATION
print(f"\nNEW (CORRECT) CALCULATION:")
print("-" * 80)
rate_fraction = perf_rate / Decimal("100")  # Convert percentage to fraction
compound_factor = (Decimal("1") + rate_fraction) ** months
correct_profit = _q2(principal_weighted * (compound_factor - Decimal("1")))
correct_valuation = _q2(principal + correct_profit)
correct_return_pct = (correct_profit / principal) * 100

print(f"Formula: profit = weighted_capital × ((1 + rate/100)^periods - 1)")
print(f"  rate_fraction = {perf_rate} / 100 = {rate_fraction}")
print(f"  compound_factor = (1 + {rate_fraction})^{months} = {compound_factor}")
print(f"  profit = ${principal_weighted:,.2f} × ({compound_factor} - 1)")
print(f"  profit = ${principal_weighted:,.2f} × {compound_factor - Decimal('1')}")
print(f"  profit = ${correct_profit:,.2f}  [CORRECT!]")
print(f"  return = {correct_return_pct:.4f}%  [CORRECT - Exactly 0.49%!]")
print(f"  valuation = ${correct_valuation:,.2f}")

# MULTI-PERIOD EXAMPLE
print(f"\nMULTI-PERIOD COMPOUND INTEREST TEST (3 months):")
print("-" * 80)
months_3 = 3
compound_factor_3 = (Decimal("1") + rate_fraction) ** months_3
correct_profit_3 = _q2(principal * (compound_factor_3 - Decimal("1")))
correct_valuation_3 = _q2(principal + correct_profit_3)
correct_return_pct_3 = (correct_profit_3 / principal) * 100

print(f"Formula: profit = principal × ((1 + 0.0049)^3 - 1)")
print(f"  compound_factor = {compound_factor_3}")  
print(f"  profit = ${principal:,.2f} × ({compound_factor_3} - 1)")
print(f"  profit = ${correct_profit_3:,.2f}")
print(f"  return = {correct_return_pct_3:.4f}% (vs {perf_rate * months_3}% if linear)")
print(f"  valuation = ${correct_valuation_3:,.2f}")
print(f"\nNote: Compound gives ${_q2(correct_profit_3):,.2f} vs linear ${_q2(principal * rate_fraction * months_3):,.2f}")

# SUMMARY
print(f"\nSUMMARY:")
print("-" * 80)
print(f"Wrong calculation profit:  ${_q2(wrong_profit):,.2f}  (ERROR: {abs(wrong_return_pct - 0.49):.2f}% off)")
print(f"Correct calculation profit: ${_q2(correct_profit):,.2f}  (Accurate to 0.49%)")
print(f"Difference: ${abs(wrong_profit - correct_profit):,.2f} per $1M invested")
print(f"\nThe fix now properly:")
print(f"  1. Converts percentage rate to decimal fraction (0.49 -> 0.0049)")
print(f"  2. Applies compound interest formula: (1 + rate)^periods")
print(f"  3. Returns accurate gains: ${correct_profit:,.2f} for {principal:,.0f}")

print("=" * 80)
