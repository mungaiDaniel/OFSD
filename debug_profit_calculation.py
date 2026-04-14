"""
Debug script to show the exact calculation discrepancy
and test the correct formulas
"""
from decimal import Decimal, ROUND_HALF_UP

def _q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimal places"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _to_decimal(value) -> Decimal:
    """Convert to Decimal"""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ============ AXIOM FUND SCENARIO ============
print("=" * 70)
print("AXIOM FUND VALUATION - MAY 2026")
print("=" * 70)

# Input values
principal = _to_decimal("2046000.00")  # Actual Axiom principal
performance_rate_input = _to_decimal("0.49")  # User enters 0.49 (meaning 0.49%)
month_days = 31  # May 2026 has 31 days

print(f"\nInput Values:")
print(f"  Principal:           ${principal:,.2f}")
print(f"  Performance Rate:    {performance_rate_input}%")
print(f"  Month Days:          {month_days}")

# ────────────────────────────────────────────────────
# WRONG CALCULATION (current code)
# ────────────────────────────────────────────────────
print(f"\n{'CURRENT (WRONG) CALCULATION':─^70}")
performance_rate_as_fraction = performance_rate_input / Decimal("100")  # 0.49 / 100 = 0.0049
wrong_profit_calc = principal * performance_rate_input  # WRONG: multiplying by 0.49 directly
print(f"If perf_rate is treated as raw value (0.49):")
print(f"  Profit = ${principal:,.2f} × {performance_rate_input}")
print(f"  Profit = ${wrong_profit_calc:,.2f}")
print(f"  This would give a {wrong_profit_calc/principal*100:.2f}% return!")

# ────────────────────────────────────────────────────
# CORRECT CALCULATION
# ────────────────────────────────────────────────────
print(f"\n{'CORRECT CALCULATION':─^70}")
correct_profit = principal * performance_rate_as_fraction
correct_valuation = principal + correct_profit
print(f"Formula: Profit = Principal × (Rate / 100)")
print(f"  Profit = ${principal:,.2f} × ({performance_rate_input} / 100)")
print(f"  Profit = ${principal:,.2f} × {performance_rate_as_fraction}")
print(f"  Profit = ${correct_profit:,.2f} ✓")
print(f"\nProjected Valuation:")
print(f"  = Principal + Profit")
print(f"  = ${principal:,.2f} + ${correct_profit:,.2f}")
print(f"  = ${correct_valuation:,.2f}")

# ────────────────────────────────────────────────────
# COMPOUND INTEREST (for multiple periods)
# ────────────────────────────────────────────────────
print(f"\n{'COMPOUND INTEREST FORMULA':─^70}")
num_periods = 1  # Single month
compound_valuation = principal * ((Decimal("1") + performance_rate_as_fraction) ** num_periods)
compound_profit = compound_valuation - principal
print(f"For {num_periods} period:")
print(f"  Valuation = Principal × (1 + Rate)^Periods")
print(f"  Valuation = ${principal:,.2f} × (1 + {performance_rate_as_fraction})^{num_periods}")
print(f"  Valuation = ${principal:,.2f} × {(Decimal("1") + performance_rate_as_fraction) ** num_periods}")
print(f"  Valuation = ${compound_valuation:,.2f}")
print(f"  Profit    = ${compound_profit:,.2f}")

# ────────────────────────────────────────────────────
# Pro-rata calculation (if not full month)
# ────────────────────────────────────────────────────
print(f"\n{'PRO-RATA CALCULATION (partial months)':─^70}")
days_active = 25  # Example: investor active for 25 out of 31 days
prorate_profit = principal * performance_rate_as_fraction * (Decimal(days_active) / Decimal(month_days))
prorate_valuation = principal + prorate_profit
print(f"For {days_active} days active out of {month_days}:")
print(f"  Profit = Principal × Rate × (DaysActive / TotalMonthDays)")
print(f"  Profit = ${principal:,.2f} × {performance_rate_as_fraction} × ({days_active}/{month_days})")
print(f"  Profit = ${prorate_profit:,.2f}")
print(f"  Valuation = ${prorate_valuation:,.2f}")

print(f"\n{'SUMMARY':─^70}")
print(f"✓ Correct single-month profit:  ${_q2(correct_profit):,.2f}")
print(f"✗ Avoid:                        ${_q2(principal * performance_rate_input):,.2f}")
print("=" * 70)
