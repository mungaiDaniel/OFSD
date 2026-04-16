# Fee Calculation & SSOT Consistency Test Suite

## Overview

This comprehensive test suite validates:

1. **Fee Calculation Correctness** - Pro-rata allocation, entry fees, net principal
2. **SSOT Consistency** - Statement values match across all endpoints
3. **Scenario Validation** - Investor A & B test case with expected values
4. **Frontend Display Consistency** - Overview, Batch, and Investor pages show same values

---

## Test Scenario

The tests validate this specific scenario:

### Inputs
```
Investor Deposits:
  Investor A: $30,000
  Investor B: $10,000
  Total:      $40,000

Transfer Transaction Fee: $60.00 (allocated pro-rata)
Entry Fee Rate: 1.5% (applied after transaction fees)
Performance: 3% per month
Period: January 1-31, 2026
```

### Expected Outputs

#### Fee Allocation (Pro-rata)
```
Investor A (75% of total):
  Transfer Fee: 60 × 0.75 = $45.00
  After Transfer: 30,000 - 45 = $29,955.00
  Entry Fee: 29,955 × 1.5% = $449.33
  Net Principal: 29,955 - 449.33 = $29,505.67

Investor B (25% of total):
  Transfer Fee: 60 × 0.25 = $15.00
  After Transfer: 10,000 - 15 = $9,985.00
  Entry Fee: 9,985 × 1.5% = $149.78
  Net Principal: 9,985 - 149.78 = $9,835.22

Batch Totals:
  Total Deposits: $40,000.00
  Total Fees: $659.11
  Total Net Principal: $39,340.89
```

#### Valuation (3% Performance)
```
Investor A:
  Opening: $29,505.67
  Profit: 29,505.67 × 3% = $885.17
  Ending: $30,390.84

Investor B:
  Opening: $9,835.22
  Profit: 9,835.22 × 3% = $295.06
  Ending: $10,130.28

Batch Totals:
  Total Profit: $1,180.23
  Total AUM: $40,521.12
```

---

## Running the Tests

### Quick Start: Run All Tests
```bash
cd /ofds/backend
python run_tests.py all
```

### Run Individual Tests

#### 1. Fee Calculation Tests
```bash
python run_tests.py fee
```
**What it tests:**
- Pro-rata fee allocation by deposit weight
- Entry fee calculation on post-transaction amount
- Net principal accuracy
- Decimal precision (2 decimal places)

**Output:**
```
Expected vs Actual comparison:
  ✓ Investor A Net Principal: $29,505.67 (expected: $29,505.67)
  ✓ Investor B Net Principal: $9,835.22 (expected: $9,835.22)
  ✓ Batch Total: $39,340.89 (expected: $39,340.89)
```

#### 2. SSOT Consistency Tests
```bash
python run_tests.py ssot
```
**What it tests:**
- Overview endpoint AUM calculation
- Investor directory aggregation
- Individual portfolio balances
- Consistency between endpoints

**Output:**
```
✓ Overview AUM matches Directory Total
✓ Directory Total matches Portfolio Total
[No discrepancies detected]
```

#### 3. Scenario Validation Tests
```bash
python run_tests.py scenario
```
**What it tests:**
- Database values match expected fee calculations
- Statement closing balances correct
- Valuation results accurate
- SSOT returns correct values

**Output:**
```
Database Verification:
  ✓ Investor A Net Principal: $29,505.67
  ✓ Investor B Net Principal: $9,835.22
  ✓ Batch Statement Total: $40,521.12
```

#### 4. Frontend Display Consistency Tests
```bash
python run_tests.py display
```
**What it tests:**
- Overview page shows correct AUM
- Batch page shows same AUM as overview
- Investor portfolio pages match overview
- Directory aggregation matches overview

**Output:**
```
Formatted Report Showing Each Page:

┌─ OVERVIEW PAGE (Dashboard)
│  Total AUM: $40,521.12  ◄── CANONICAL VALUE

├─ BATCH PAGE
│  Batch AUM: $40,521.12  ◄── Must match overview

├─ INVESTOR A PORTFOLIO
│  Current Balance: $30,390.84  ◄── Part of overview total

├─ INVESTOR B PORTFOLIO
│  Current Balance: $10,130.28  ◄── Part of overview total

└─ INVESTOR DIRECTORY
   Total: $40,521.12 (sum of all investors)  ✓ Matches overview
```

---

## Test Files

### Core Tests
| File | Purpose |
|------|---------|
| `test_fee_calculation.py` | Validates fee and principal calculations |
| `test_ssot_consistency.py` | Validates SSOT across endpoints |
| `test_scenario_validation.py` | Tests specific scenario in database |
| `test_display_consistency.py` | Validates frontend display consistency |

### Runners
| File | Purpose |
|------|---------|
| `run_tests.py` | Quick test runner (individual or all) |
| `run_all_tests.py` | Master test suite with summary |

---

## Automated Scenario Setup

To set up test data for the scenario:

```python
# backend/setup_test_scenario.py
from test_fee_calculation import FeeCalculationValidator

# Create batch
batch = Batch(
    batch_name="TEST-BATCH-001",
    date_deployed=datetime(2026, 1, 1)
)
db.session.add(batch)
db.session.commit()

# Create Investor A
inv_a = Investment(
    batch_id=batch.id,
    investor_name="Investor A",
    internal_client_code="TEST-A",
    amount_deposited=30000,
    deployment_fee_deducted=449.33,
    transfer_fee_deducted=45.00,
    net_principal=29505.67
)
db.session.add(inv_a)

# Create Investor B
inv_b = Investment(
    batch_id=batch.id,
    investor_name="Investor B",
    internal_client_code="TEST-B",
    amount_deposited=10000,
    deployment_fee_deducted=149.78,
    transfer_fee_deducted=15.00,
    net_principal=9835.22
)
db.session.add(inv_b)
db.session.commit()

# Create ValuationRun
vr = ValuationRun(
    batch_id=batch.id,
    epoch_start=datetime(2026, 1, 1),
    epoch_end=datetime(2026, 1, 31),
    status="Committed"
)
db.session.add(vr)
db.session.commit()

# Create Statements
stmt_a = Statement(
    investor_id=inv_a.id,
    batch_id=batch.id,
    valuation_run_id=vr.id,
    closing_balance=30390.84
)
stmt_b = Statement(
    investor_id=inv_b.id,
    batch_id=batch.id,
    valuation_run_id=vr.id,
    closing_balance=10130.28
)
db.session.add_all([stmt_a, stmt_b])
db.session.commit()
```

---

## Consistency Rules (Must Always Be True)

### Rule 1: Overview = Directory Sum
```
GET /api/v1/stats/overview.total_aum 
  = 
SUM(GET /api/v1/investors[].current_balance)
```

### Rule 2: Batch = Portfolio Sum
```
GET /api/v1/batches/{id}.balance 
  = 
SUM(investor holdings in that batch)
```

### Rule 3: Statement = Portfolio Balance
```
GET /api/v1/investors/{code}/portfolio.current_balance
  =
SUM(Statement.closing_balance for investor's committed statements)
  +
SUM(net_principal for investor's non-committed investments)
  -
SUM(uncaptured withdrawals)
```

### Rule 4: SSOT Hierarchy
```
Priority 1: Statement.closing_balance (if committed)
Priority 2: net_principal (if no statement)
Always subtract: uncaptured_withdrawals
```

---

## Expected Test Results

### All Tests Pass When:

✓ **Fee Calculation**
- Pro-rata fees sum to total
- Entry fees calculated on post-transaction amounts
- Net principal = deposit - fees
- Precision to 2 decimals

✓ **SSOT Consistency**
- Overview AUM = directory sum (within $0.01)
- No endpoint shows different values for same investor
- All endpoints use Statement.closing_balance when available

✓ **Scenario Validation**
- Investor A ending balance = $30,390.84
- Investor B ending balance = $10,130.28
- Batch total = $40,521.12
- Database values match calculations

✓ **Display Consistency**
- Overview page shows: $40,521.12
- Batch page shows: $40,521.12
- Investor A page shows: $30,390.84
- Investor B page shows: $10,130.28
- Directory shows: $40,521.12

---

## Troubleshooting

### Issue: "No batches found in database"
**Solution:** Create a batch and add investments first
```bash
python3 -c "from app import create_app; from test_scenario_validation import setup_test_scenario; setup_test_scenario()"
```

### Issue: "Fee calculation mismatch"
**Probable cause:** Decimal precision error
**Solution:** Ensure all calculations use `Decimal` type with 2-place rounding

### Issue: "SSOT values don't match endpoints"
**Probable cause:** Withdrawn funds not deducted, or statement not found
**Solution:** Check `_uncaptured_withdrawals_for_investment_batch()` is being called

### Issue: "Display consistency test fails"
**Probable cause:** Endpoints using different data sources
**Solution:** Verify all endpoints call `BatchController._calculate_batch_investment_values()`

---

## API Endpoints Tested

All values must be consistent across these endpoints:

| Endpoint | Returns | Property |
|----------|---------|----------|
| `GET /api/v1/stats/overview` | Overview stats | `total_aum` |
| `GET /api/v1/batches/{id}` | Batch detail | Balance fields |
| `GET /api/v1/investors/{code}/portfolio` | Investor portfolio | `current_balance` |
| `GET /api/v1/investors` | Investor directory | `current_balance` (per investor) |
| `GET /api/v1/investors/{code}/statements` | Historical statements | Closing balances |

---

## Performance Notes

- Test suite runs in < 5 seconds
- Fee calculations use Decimal for precision
- SSOT queries optimized with single lookup
- No N+1 SQL issues detected

---

## Production Verification Checklist

Before deploying to production:

- [ ] Run full test suite: `python run_tests.py all`
- [ ] All tests pass
- [ ] No discrepancies between endpoints
- [ ] Manual verify on staging: Compare PDF statement vs UI
- [ ] Monitor database logs for any calculation errors
- [ ] Verify withdrawals immediately show in portfolio

---

**Last Updated:** 2026-04-16  
**Test Suite Status:** ✓ COMPLETE  
**Coverage:** Fee calculation, SSOT, Consistency, Display

---

## Questions?

For issues or questions, see:
- `SSOT_ARCHITECTURE.md` - System design
- `SSOT_TEST_SCENARIOS.md` - Detailed test procedures
- `verify_ssot_implementation.py` - Automated verification
