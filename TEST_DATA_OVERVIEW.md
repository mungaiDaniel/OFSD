# 📊 Test Data Overview

## Excel File Contents: `investors_test_15.xlsx`

### AXIOM FUND (7 Investors)

| # | Name | Email | Code | Amount | Fund | Date |
|---|------|-------|------|--------|------|------|
| 1 | John Smith | john.smith@example.com | AXIOM-001 | $50,000.00 | Axiom | 2026-03-10 |
| 2 | Jane Doe | jane.doe@example.com | AXIOM-002 | $50,000.00 | Axiom | 2026-03-10 |
| 3 | Michael Johnson | michael.j@example.com | AXIOM-003 | $50,000.00 | Axiom | 2026-03-10 |
| 4 | Sarah Williams | sarah.w@example.com | AXIOM-004 | $50,000.00 | Axiom | 2026-03-10 |
| 5 | David Brown | david.b@example.com | AXIOM-005 | $50,000.00 | Axiom | 2026-03-10 |
| 6 | Emma Davis | emma.d@example.com | AXIOM-006 | $50,000.00 | Axiom | 2026-03-10 |
| 7 | Robert Wilson | robert.w@example.com | AXIOM-007 | $50,000.00 | Axiom | 2026-03-10 |
| | | | **SUBTOTAL** | **$350,000.00** | | |

---

### ATIUM FUND (8 Investors)

| # | Name | Email | Code | Amount | Fund | Date |
|---|------|-------|------|--------|------|------|
| 8 | Lisa Anderson | lisa.a@example.com | ATIUM-001 | $50,000.00 | Atium | 2026-03-10 |
| 9 | James Taylor | james.t@example.com | ATIUM-002 | $50,000.00 | Atium | 2026-03-10 |
| 10 | Mary Martinez | mary.m@example.com | ATIUM-003 | $50,000.00 | Atium | 2026-03-10 |
| 11 | William Garcia | william.g@example.com | ATIUM-004 | $50,000.00 | Atium | 2026-03-10 |
| 12 | Patricia Robinson | patricia.r@example.com | ATIUM-005 | $50,000.00 | Atium | 2026-03-10 |
| 13 | Christopher Lee | christopher.l@example.com | ATIUM-006 | $50,000.00 | Atium | 2026-03-10 |
| 14 | Jennifer White | jennifer.w@example.com | ATIUM-007 | $50,000.00 | Atium | 2026-03-10 |
| 15 | Andrew Harris | andrew.h@example.com | ATIUM-008 | $50,000.00 | Atium | 2026-03-10 |
| | | | **SUBTOTAL** | **$400,000.00** | | |

---

## 📈 Portfolio Summary

```
AXIOM FUND
├── Investors: 7
├── Total Capital: $350,000.00
├── Avg Per Investor: $50,000.00
└── Deployment Date: 2026-03-10

ATIUM FUND
├── Investors: 8
├── Total Capital: $400,000.00
├── Avg Per Investor: $50,000.00
└── Deployment Date: 2026-03-10

BATCH TOTALS
├── Total Investors: 15
├── Total Capital: $750,000.00  ← This is MORE than $600k to show different fund sizes
└── Deployment Date: 2026-03-10
```

---

## 💰 Expected Profit Calculations (March Performance)

### Axiom Fund Performance
```
Gross Profit:        $100,000.00
Transaction Costs:   -$5,000.00
────────────────────────────────
Net Profit:          $95,000.00

Days Active (Mar 10-31): 6 days → 13 days (if testing by March 31)
```

### Atium Fund Performance
```
Gross Profit:        $75,000.00
Transaction Costs:   -$2,500.00
────────────────────────────────
Net Profit:          $72,500.00

Days Active (Mar 10-31): 6 days → 13 days (if testing by March 31)
```

---

## 🧮 Sample Calculation: Axiom Distribution

**As of March 16, 2026 (6 days active):**

```
INVESTOR: John Smith (AXIOM-001)
Amount Deposited:        $50,000.00
Days Active:             6 days
Weighted Capital:        $50,000 × 6 = $300,000

FUND TOTALS:
All Axiom Investors:     7 × $50,000 = $350,000
Total Weighted Capital:  7 × $300,000 = $2,100,000

PROFIT SHARE CALCULATION:
Profit Share % = ($300,000 / $2,100,000) × 100 = 14.2857143%

PROFIT ALLOCATION:
Net Profit Available:    $95,000.00
Allocated to John:       (14.2857143% / 100) × $95,000 = $13,571.43

VERIFICATION:
Each of 7 investors gets: $13,571.43
Total allocated:         7 × $13,571.43 = $95,000.01 ✓ (within rounding)
```

---

## 📋 What You'll See After Each Test

### After Upload Excel
```
✅ Funds Created:
   - Axiom (AX-Q1-2026): $350,000 capital, 7 investors
   - Atium (AT-Q1-2026): $400,000 capital, 8 investors  ← Note: $400k not $250k

✅ Investments Created: 15 total
```

### After Recording Performance
```
✅ Axiom Performance (performance_id: 201):
   - Gross: $100,000
   - Costs: $5,000
   - Net: $95,000
   - Cumulative: $95,000 (first record)
   - Report Date: 2026-03-31

✅ Atium Performance (performance_id: 202):
   - Gross: $75,000
   - Costs: $2,500
   - Net: $72,500
   - Cumulative: $72,500 (first record)
   - Report Date: 2026-03-31
```

### After Calculate All Funds
```
✅ Distributions Created: 15 total

AXIOM (7 distributions):
├── John Smith (AXIOM-001): $50k × 6d = 14.2857% share = $13,571.43
├── Jane Doe (AXIOM-002): $50k × 6d = 14.2857% share = $13,571.43
├── Michael Johnson (AXIOM-003): $50k × 6d = 14.2857% share = $13,571.43
├── Sarah Williams (AXIOM-004): $50k × 6d = 14.2857% share = $13,571.43
├── David Brown (AXIOM-005): $50k × 6d = 14.2857% share = $13,571.43
├── Emma Davis (AXIOM-006): $50k × 6d = 14.2857% share = $13,571.43
└── Robert Wilson (AXIOM-007): $50k × 6d = 14.2857% share = $13,571.43
    ─────────────────────────────────────────
    TOTAL AXIOM ALLOCATED: $95,000.01

ATIUM (8 distributions):
├── Lisa Anderson (ATIUM-001): $50k × 6d = 12.5000% share = $9,062.50
├── James Taylor (ATIUM-002): $50k × 6d = 12.5000% share = $9,062.50
├── Mary Martinez (ATIUM-003): $50k × 6d = 12.5000% share = $9,062.50
├── William Garcia (ATIUM-004): $50k × 6d = 12.5000% share = $9,062.50
├── Patricia Robinson (ATIUM-005): $50k × 6d = 12.5000% share = $9,062.50
├── Christopher Lee (ATIUM-006): $50k × 6d = 12.5000% share = $9,062.50
├── Jennifer White (ATIUM-007): $50k × 6d = 12.5000% share = $9,062.50
└── Andrew Harris (ATIUM-008): $50k × 6d = 12.5000% share = $9,062.50
    ─────────────────────────────────────────
    TOTAL ATIUM ALLOCATED: $72,500.00

BATCH TOTALS:
├── Total Capital: $750,000.00
├── Total Profit: $167,500.01
├── ROI: 22.33%
└── Distributions: 15
```

### After Batch Summary
```
✅ Batch Overview:
   Batch Name: Q1-2026 Portfolio
   Date Deployed: 2026-03-10
   Duration: 30 days
   Expected Close: 2026-04-09
   
   Status: ACTIVE
   
   Total Investors: 15
   Total Capital: $750,000.00
   Total Profit: $167,500.01
   ROI: 22.33%

   Fund Breakdown:
   ├── Axiom: 7 investors, $350,000 capital, $95,000 profit
   └── Atium: 8 investors, $400,000 capital, $72,500 profit
```

### PDF Report Structure
```
┌─────────────────────────────┐
│  Q1-2026 BATCH STATEMENT    │
├─────────────────────────────┤
│ Batch Name: Q1-2026         │
│ Deployed: 2026-03-10        │
│ Expected Close: 2026-04-09  │
│ Total Capital: $750,000.00  │
└─────────────────────────────┘

┌──────────── AXIOM FUND ──────────────┐
│ Total Capital: $350,000.00           │
│ Investors: 7                         │
│                                      │
│ [INVESTMENTS TABLE]                  │
│ Code      │ Name    │ Amount │ Date  │
│ AXIOM-001 │ John    │ $50k   │ 03/10 │
│ ...       │ ...     │ ...    │ ...   │
│                                      │
│ [DISTRIBUTIONS TABLE]                │
│ Code      │ Days │ Share % │ Profit │
│ AXIOM-001 │ 6   │ 14.29% │ $13.5k │
│ ...       │ ... │ ...    │ ...    │
│                                      │
│ Total Allocated: $95,000.00          │
└──────────────────────────────────────┘

┌──────────── ATIUM FUND ───────────────┐
│ Total Capital: $400,000.00            │
│ Investors: 8                          │
│                                       │
│ [INVESTMENTS TABLE]                   │
│ Code      │ Name     │ Amount │ Date  │
│ ATIUM-001 │ Lisa     │ $50k   │ 03/10 │
│ ...       │ ...      │ ...    │ ...   │
│                                       │
│ [DISTRIBUTIONS TABLE]                 │
│ Code      │ Days │ Share % │ Profit  │
│ ATIUM-001 │ 6   │ 12.50%  │ $9.06k  │
│ ...       │ ... │ ...     │ ...     │
│                                       │
│ Total Allocated: $72,500.00           │
└───────────────────────────────────────┘

┌────────── BATCH SUMMARY ───────────┐
│ Total Capital:    $750,000.00      │
│ Total Profit:     $167,500.01      │
│ Total Investors:  15               │
│ ROI:              22.33%           │
│ Status:           ACTIVE           │
└────────────────────────────────────┘
```

---

## 🎯 Key Differences to Note

**Why $400k for Atium instead of $250k?**
- This tests your system with different fund sizes
- Axiom: 7 investors × $50k = $350,000
- Atium: 8 investors × $50k = $400,000
- Total: $750,000 (not just $600k)

**Why different investor counts?**
- Tests fund-specific calculations
- Shows profit share percentages differ (14.29% vs 12.50%)
- Validates weighted capital with different fund totals

**What this catches:**
- ✅ Per-fund profit allocation (not batch-wide)
- ✅ Different profit shares based on fund size
- ✅ Accurate decimal calculations
- ✅ Fund independence in calculations

---

## 📥 Generate and Test

1. Run: `python create_test_excel.py`
2. Opens: `investors_test_15.xlsx` in your working directory
3. Upload via: `POST /batches/1/upload-excel` with file
4. Verify: All 15 investors with correct funds assigned

**You're ready to test!** 🚀
