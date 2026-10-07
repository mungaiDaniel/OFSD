# Valuation Mathematics Fix - Axiom Fund

## Current Issue
The system is calculating a massive $1,882,546.89 gain instead of the correct $10,025.40 for the Axiom fund.

## Correct Calculation (What We Need)
```
Principal (Initial Deposit):    $2,046,000.00
Performance Rate:               0.49%
Month Days:                     31 days

Profit = Principal × (Rate / 100)
Profit = $2,046,000.00 × 0.0049
Profit = $10,025.40 ✓

Projected Valuation = Principal + Profit
Projected Valuation = $2,046,000.00 + $10,025.40
Projected Valuation = $2,056,025.40 ✓
```

## Problem Root Cause
The current code in `valuation_service.py` (line ~719) calculates:
```python
total_profit = _q2(total_weighted_capital_for_allocation * perf_rate)
```

### Issues:
1. **Weighted Capital != Principal**: The weighted capital uses a day-ratio which reduces the capital
2. **Missing Month Adjustment**: For a single month period, the calculation needs to account for the full month
3. **No Compound Interest Applied**: Despite compound interest being mentioned, it's not being properly calculated

## Correct Formula for Single Month
```
Profit = Principal × (PerformanceRate / 100) × (DaysActive / MonthDays)
```

For a full month:
```
Profit = Principal × (PerformanceRate / 100) × (31 / 31)
Profit = Principal × (PerformanceRate / 100)
```

## Compound Interest Formula (for multiple periods)
```
Projected Valuation = Principal × (1 + Rate/100)^Periods
```

For single period:
```
Projected Valuation = Principal × (1 + 0.0049)
Projected Valuation = Principal × 1.0049
```

## What Needs to Change
1. Use the actual principal amount ($2,046,000) not weighted_capital
2. Apply performance rate correctly as a percentage
3. For compound scenarios, use compound formula: `(1 + rate)^periods`
4. Ensure withdrawal-adjusted capital is used for subsequent periods

## Implementation Areas
- `_build_investor_inputs()`: Ensure principal is correctly identified
- `create_epoch_ledger_for_fund()`: Fix profit calculation (line ~719)
- `preview_epoch_for_fund()`: Same profit calculation fix
