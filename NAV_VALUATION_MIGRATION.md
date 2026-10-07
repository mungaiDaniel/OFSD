# NAV-Based Valuation System - Migration Guide

## Overview

The OFSD system has migrated from a **Percentage-Based Epoch Ledger** model to a **Share-Based NAV (Net Asset Value)** model. This aligns the system with the Mauritius Head Office requirements.

## Key Files

### New Files (NAV-Based)
- **`app/logic/nav_valuation_service.py`** - Core NAV valuation service
- **`app/Funds/share_class.py`** - Share class model
- **`app/Funds/nav_history.py`** - NAV price history tracking
- **`app/Funds/investor_shares.py`** - Investor share holdings
- **`app/Valuation/valuation_snapshot.py`** - Point-in-time valuation records
- **Migrations:**
  - `007_share_classes_table.py`
  - `008_nav_history_table.py`
  - `009_investor_shares_table.py`
  - `010_valuation_snapshots_table.py`
  - `011_add_batches_share_columns.py`
  - `012_add_investments_share_columns.py`
  - `013_populate_investments_share_class_data.py` (data migration)

### Updated Files
- **`app/logic/valuation_service.py`** - Now a compatibility wrapper importing from nav_valuation_service.py
- **`app/Batch/model.py`** - Added share_class_id and related columns
- **`app/Investments/model.py`** - Added share_class_id and deposit_date columns

## Migration Path

### 1. Database Schema (Run Migrations)

```bash
cd backend
flask db upgrade
```

This will:
1. Create `share_classes` table
2. Create `nav_history` table
3. Create `investor_shares` table
4. Create `valuation_snapshots` table
5. Add columns to `batches` table
6. Add columns to `investments` table
7. Automatically populate `share_class_id` for existing investments (where possible)

### 2. Create Share Classes

Manually create share classes for existing funds:

```python
from app.database.database import db
from app.Funds import ShareClass
from app.Batch.core_fund import CoreFund

# Create share classes for each fund
axiom = CoreFund.query.filter_by(fund_name="Axiom").first()
share_class = ShareClass(
    core_fund_id=axiom.id,
    class_name="Class I - KES",
    class_code="AxiomI-KES",
    currency="KES",
    is_active=True
)
db.session.add(share_class)
db.session.commit()
```

### 3. Backload Historical Data

For existing investments, populate:
- `investor_shares` - Historical share holdings with deployment NAV
- `nav_history` - Historical NAV prices from deployment confirmations

```python
from app.Funds import InvestorShares, NavHistory
from datetime import date
from decimal import Decimal

# Create investor shares record
inv_shares = InvestorShares(
    investment_id=1,
    share_class_id=1,
    batch_id=1,
    shares_owned=Decimal("771.92"),
    deployment_nav=Decimal("1330.00"),
    deployment_date=date(2026, 3, 15),
    is_active=True
)
db.session.add(inv_shares)

# Create NAV history record
nav_hist = NavHistory(
    share_class_id=1,
    nav_date=date(2026, 3, 15),
    nav_per_share=Decimal("1330.00"),
    total_fund_nav=Decimal("5000000.00"),
    source="deployment"
)
db.session.add(nav_hist)
db.session.commit()
```

### 4. Execute Valuations

Use the new NAV-based service:

```python
from app.logic.valuation_service import PortfolioValuationService, NavInput
from datetime import date
from decimal import Decimal

# Prepare NAV inputs
nav_inputs = [
    NavInput(
        share_class_id=1,
        nav_per_share=Decimal("1389.5737"),
        total_fund_nav=Decimal("1072636.69")
    )
]

# Execute valuation (creates snapshots and nav_history)
results = PortfolioValuationService.execute_valuation(
    valuation_date=date(2026, 4, 10),
    nav_inputs=nav_inputs,
    dry_run=False  # Set to True for validation without persistence
)

for result in results:
    print(f"Class {result.share_class_id}: Created {result.snapshots_created} snapshots")
    print(f"Reconciliation: ${result.system_total} vs ${result.total_fund_nav} (diff: ${result.reconciliation_diff})")
```

## Core Formulas

### Market Value Calculation
```
Market Value = Shares Owned × Current NAV Per Share
```

### Performance Percentage
```
Performance % = ((Current NAV - Deployment NAV) / Deployment NAV) × 100
```

### Reconciliation Check
```
System Total = Sum(Shares × Current NAV)
Must satisfy: |System Total - Total Fund NAV| ≤ $1.00 (configurable tolerance)
```

## Data Structure

### SampleValuation Flow

**Input:**
- Valuation Date: 2026-04-10
- Share Class 1 (Class I - KES): NAV = 1,389.5737, Total Fund NAV = $1,072,636.69

**Processing:**
1. Load all active investor_shares for class 1
2. For Joy Kendi: 771.92 shares @ 1,389.5737 NAV
   - Market Value = 771.92 × 1,389.5737 = $1,072,636.69
   - Deployment NAV was 1,330.00
   - Performance = ((1,389.5737 - 1,330.00) / 1,330.00) × 100 = 4.52%
3. Create ValuationSnapshot record with these values
4. Create NavHistory record (source="valuation")

**Output:**
- 1 ValuationSnapshot per investor holding
- 1 NavHistory record per share class
- Reconciliation validated

## Key Constants

All in `app/logic/nav_valuation_service.py`:

```python
RECONCILIATION_TOLERANCE = Decimal("1.00")  # $1.00 tolerance
NAV_DECIMAL_PLACES = 6  # e.g., 1,389.5737
MARKET_VALUE_DECIMAL_PLACES = 2  # e.g., 1,072,636.69
```

To adjust tolerance (e.g., $10.00):
```python
from app.logic.nav_valuation_service import PortfolioValuationService
PortfolioValuationService.RECONCILIATION_TOLERANCE = Decimal("10.00")
```

## Error Handling

### Reconciliation Error
Raised when system total deviates > tolerance from fund NAV:
```
ValueError: Reconciliation failed for share class 1: 
System total $1,072,635.50 vs Fund NAV $1,072,636.69 
(diff: $1.19, tolerance: $1.00)
```

### Missing NAV History
If querying investor valuation with no NAV:
```python
result = PortfolioValuationService.get_investor_valuation(investor_shares_id=1)
# Returns: {"error": "No NAV history found for share class"}
```

## Decimal Precision

**Important:** All financial calculations use Python `Decimal` type, never `float`.

```python
# ✅ Correct
from decimal import Decimal
nav = Decimal("1389.5737")
shares = Decimal("771.92")
market_value = shares * nav

# ❌ Wrong - will lose precision
nav = 1389.5737  # float
shares = 771.92   # float
market_value = shares * nav  # precision loss
```

## Backward Compatibility

Existing code importing from `app.logic.valuation_service` continues to work:

```python
# This import still works and uses NAV-based service
from app.logic.valuation_service import PortfolioValuationService
```

The old percentage-based epoch ledger code is preserved at the end of `valuation_service.py` for reference and potential rollback.

## Rollback (If Needed)

1. Uncomment the old code in `valuation_service.py`
2. Comment out the NAV-based imports
3. Revert database migrations (if appropriate):
   ```bash
   flask db downgrade
   ```

## Testing

```python
# Test dry-run (validation without persistence)
results = PortfolioValuationService.execute_valuation(
    valuation_date=date(2026, 4, 10),
    nav_inputs=nav_inputs,
    dry_run=True  # No database changes
)

# Query current portfolio value
portfolio = PortfolioValuationService.get_current_portfolio_value(share_class_id=1)
print(f"Total Market Value: ${portfolio['total_market_value']}")

# Query individual investor valuation
investor_val = PortfolioValuationService.get_investor_valuation(investor_shares_id=1)
print(f"Market Value: ${investor_val['market_value']}")
print(f"Performance: {investor_val['performance_pct']}%")
```

## Support / Issues

For questions about:
- **Share class creation:** See `app/Funds/share_class.py`
- **NAV history management:** See `app/Funds/nav_history.py`
- **Investor share tracking:** See `app/Funds/investor_shares.py`
- **Valuation snapshots:** See `app/Valuation/valuation_snapshot.py`
- **Batch updates:** See `app/Batch/model.py` for new columns
- **Investment updates:** See `app/Investments/model.py` for new columns
