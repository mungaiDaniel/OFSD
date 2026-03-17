# OFDS Multi-Fund Portfolio Refactoring Guide

## 📋 Overview

The OFDS system has been refactored to support **multiple funds within a single batch** with **live weekly calculations** and **fund-specific performance tracking**. This enables managing complex offshore fund portfolios with granular reporting.

---

## 🎯 Key Changes

### 1. **Schema Evolution**

#### New Models
- **Fund Model** (`app/Batch/fund.py`): Represents individual funds (e.g., 'Axiom', 'Atium') within a batch
- **FundPerformance Model** (`app/Batch/fund.py`): Monthly/weekly performance records per fund
- **Updated Investment Model**: Now includes `fund_name` and `internal_client_code`
- **Updated ProRataDistribution Model**: Fund-aware with denormalized investor data

#### Updated Investment Model Fields
```python
investor_name: str
investor_email: str
internal_client_code: str        # NEW: Unique ID from Excel
amount_deposited: Decimal
date_deposited: datetime
date_transferred: datetime       # NEW: When capital actually transferred
fund_name: str                   # NEW: Fund assignment (Axiom/Atium)
batch_id: int (FK)
fund_id: int (FK) - NEW           # Link to specific fund
```

#### Fund Model Structure
```python
batch_id: int (FK)
fund_name: str                   # e.g., 'Axiom', 'Atium'
certificate_number: str          # Inherited from batch
total_capital: Decimal(20,2)     # Sum of all investments in fund
date_deployed: datetime
duration_days: int
date_closed: datetime (nullable)
is_active: bool
```

#### FundPerformance Model (NEW)
```python
fund_id: int (FK)
batch_id: int (FK)
gross_profit: Decimal(20,2)
transaction_costs: Decimal(20,2)
cumulative_profit: Decimal(20,2) # Running total across periods
report_date: datetime
reporting_period: str            # MONTHLY, WEEKLY, QUARTERLY
```

---

## 🚀 Live Weekly Calculation Engine

### Duration Calculation (LIVE)
**Key Difference from Previous System:**

```
OLD: Duration = date_deployed + duration_days (FIXED)
NEW: Duration = Current_Date - date_deployed (LIVE)
```

**Example:**
- Batch deployed: Mar 1, 2026
- Reporting on: Mar 23, 2026
- Duration so far: 22 days (NOT 30)
- This recalculates every week without waiting for month-end

### Days Active Formula (Updated)
```
Days Active = Max(Current_Date, Batch_End) - Max(Deposit_Date, Deployment_Date)
```

**Scenario:**
- Batch: Mar 1 - Mar 31 (planned 30 days)
- Current: Mar 23 (22 days elapsed)
- Investor deposited: Mar 10

```
Days Active = Mar 23 - Mar 10 = 13 days (LIVE)
If we waited until Mar 31 = 21 days (FINAL)
```

### Weekly Trigger
```
Week 1 (Mar 1-7):    Calculate with 7 days elapsed
Week 2 (Mar 8-14):   Calculate with 14 days elapsed
Week 3 (Mar 15-21):  Calculate with 21 days elapsed
Week 4 (Mar 22-31):  Calculate with final days
```

---

## 💰 Multi-Fund Profit Distribution

### Fund-Aware Pro-Rata Formula

```
Profit Share % = (Weighted Capital) / (Total Fund Weighted Capital) × 100
Profit Allocated = (Profit Share %) / 100 × Fund Net Profit
```

**Key Point:** Calculations are per-fund, not per-batch. 'Axiom' profit is separate from 'Atium' profit.

### Example: Two-Fund Batch

**Setup:**
```
Batch: Q1-2026-OFFSHORE
├─ Fund: Axiom (7 investors)
│  ├─ Total Capital: $350,000
│  ├─ Gross Profit: $100,000
│  └─ Transaction Costs: $5,000
│     → Net Profit: $95,000
│
└─ Fund: Atium (5 investors)
   ├─ Total Capital: $250,000
   ├─ Gross Profit: $75,000
   └─ Transaction Costs: $2,500
      → Net Profit: $72,500
```

**Calculation for Axiom Fund Only:**
```
Investor #1: $50,000 deposited Mar 10
- Days Active: 13 days
- Weighted Capital: 50,000 × 13 = 650,000

Investor #2: $40,000 deposited Mar 1
- Days Active: 22 days
- Weighted Capital: 40,000 × 22 = 880,000

... (total for all 7)
Total Weighted Capital (Axiom): 2,450,000

Investor #1 Share: (650,000 / 2,450,000) × 100 = 26.53%
Investor #1 Profit: 0.2653 × $95,000 = $25,203.50
```

**Axiom Total Distributed: $95,000**
**Atium Total Distributed: $72,500** (separate calculation)
**Batch Total: $167,500**

---

## 📤 Excel Bulk Upload Logic

### Flow Diagram
```
┌─────────────────────┐
│   Excel File        │
│  (12 investors)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Parse & Validate                    │
│  - Check required columns            │
│  - Validate numeric precision        │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Auto-Group by Fund                  │
│  Axiom: Investors 1-7  (350k)        │
│  Atium: Investors 8-12 (250k)        │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Create Fund Records (if needed)     │
│  Fund.Axiom, Fund.Atium              │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Create Investment Records           │
│  12 investments linked to funds      │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Update Fund.total_capital           │
│  Axiom: 350k, Atium: 250k            │
└─────────────────────────────────────┘
```

### Excel File Format

```
investor_name | investor_email | internal_client_code | amount(usd) | fund | date_transferred
John Doe       | john@ex.com    | AXIOM-001           | 50000.00    | Axiom| 2026-03-10
Jane Smith     | jane@ex.com    | AXIOM-002           | 40000.00    | Axiom| 2026-03-01
...
Bob Wilson     | bob@ex.com     | ATIUM-008           | 75000.00    | Atium| 2026-03-05
...
```

**Auto-Assignment (if 'fund' column missing):**
```
Investors 1-7  → Axiom
Investors 8-12 → Atium
```

### API Endpoint
```
POST /api/v1/batches/{batch_id}/upload-excel
Headers: Authorization: Bearer <token>
Body: multipart/form-data with file

Response:
{
    "created_count": 12,
    "funds": {
        "Axiom": {
            "fund_id": 1,
            "investor_count": 7,
            "total_capital": 350000.00
        },
        "Atium": {
            "fund_id": 2,
            "investor_count": 5,
            "total_capital": 250000.00
        }
    }
}
```

---

## 🔢 Live Weekly Calculations

### Use Case: Without Waiting for Monthly Performance

**Scenario:**
It's March 23, but final performance data isn't available until month-end (Mar 31).
Investors still want to see their positions and projected profits.

**Weekly Update Endpoint:**
```
GET /api/v1/batches/{batch_id}/funds/{fund_name}/weekly-update
```

**Response:**
```json
{
    "fund_name": "Axiom",
    "as_of_date": "2026-03-23T00:00:00",
    "total_capital": 350000.00,
    "total_days_active": 13,
    "investors": [
        {
            "investor_name": "John Doe",
            "internal_client_code": "AXIOM-001",
            "amount_deposited": 50000.00,
            "date_deposited": "2026-03-10T00:00:00",
            "days_active": 13,
            "expected_close_date": "2026-03-31T00:00:00"
        }
    ]
}
```

**Use in Frontend:**
- Display accrued days in real-time
- Calculate projected returns once performance is entered
- Show fund performance vs. target

---

## 🏦 Multi-Performance Tracking

### Independent Fund Management

**Key Benefit:** Record 'Axiom' performance WITHOUT affecting 'Atium'

#### Upload Axiom Performance
```
POST /api/v1/batches/{batch_id}/funds/Axiom/performance

{
    "gross_profit": 100000.00,
    "transaction_costs": 5000.00,
    "reporting_period": "MONTHLY"
}
```

**Result:** Axiom fund now has $95,000 net profit to distribute.

#### Later: Upload Atium Performance
```
POST /api/v1/batches/{batch_id}/funds/Atium/performance

{
    "gross_profit": 75000.00,
    "transaction_costs": 2500.00,
    "reporting_period": "MONTHLY"
}
```

**Result:** Atium fund now has $72,500 net profit to distribute.

**Advantage:** No need to wait for all funds to have complete data.

#### Query Fund-Specific Performance
```
GET /api/v1/batches/{batch_id}/funds/Axiom
```

Returns:
- Fund metadata
- All 7 Axiom investments
- Performance history
- Distributions (if calculated)

---

## 🧮 Pro-Rata Calculation Flow

### Step 1: Upload Excel File
```bash
POST /api/v1/batches/1/upload-excel
→ Creates Fund: Axiom, Fund: Atium
→ Creates 12 Investment records
```

### Step 2: Record Fund Performance
```bash
POST /api/v1/batches/1/funds/Axiom/performance
→ Creates FundPerformance record

POST /api/v1/batches/1/funds/Atium/performance
→ Creates FundPerformance record
```

### Step 3: Calculate Distributions
```bash
POST /api/v1/batches/1/calculate-all-funds

{
    "performance_data": {
        "Axiom": 1,    // Fund name -> Performance ID
        "Atium": 2
    }
}
```

**Service Logic:**
1. Get all unique funds in batch
2. For each fund:
   - Get all investments in fund
   - Calculate days_active (live)
   - Calculate weighted_capital
   - Calculate profit shares
   - Create ProRataDistribution records
3. Return summary with all funds

**Response:**
```json
{
    "batch_id": 1,
    "calculation_date": "2026-03-23T00:00:00",
    "distribution_count": 12,
    "total_batch_value": 167500.00,
    "funds": {
        "Axiom": {
            "investor_count": 7,
            "total_allocated": 95000.00,
            "distributions": [...]
        },
        "Atium": {
            "investor_count": 5,
            "total_allocated": 72500.00,
            "distributions": [...]
        }
    }
}
```

---

## 📊 Comprehensive Summary Endpoint

### Get Full Batch Overview
```
GET /api/v1/batches/{batch_id}/summary
```

**Response shows:**
- Batch metadata
- Fund breakdown (by fund):
  - Total capital
  - Investor count
  - Performance records count
  - Total distributed
  - Expected close date

**Use Case:** Dashboard showing portfolio overview

---

## 📄 PDF Report Generation

### Generate Investment Statements
```
GET /api/v1/batches/{batch_id}/report/pdf?download=true
```

**PDF Includes:**
- Batch summary header
- Per-fund sections:
  - Fund investments table
  - Investor details (name, code, amount, status)
  - Profit distributions by investor
  - Weighted capital breakdown

**Use Case:** Send investor statements, compliance documentation

---

## 🔧 Service Layer: MultiFundProRataService

### Core Methods

```python
# Calculate days for an investor (live calculation)
calculate_days_active(deposit_date, batch, current_date=None)
→ Returns: int (days active as of current_date)

# Weighted capital calculation
calculate_weighted_capital(amount, days_active)
→ Returns: Decimal(amount × days)

# Profit share percentage
calculate_profit_share(investor_weighted, total_weighted)
→ Returns: Decimal(0-100, 4 decimals)

# Allocate actual profit
calculate_profit_allocated(profit_share_pct, net_profit)
→ Returns: Decimal(allocated amount)

# Calculate for specific fund
calculate_fund_distributions(batch_id, fund_name, performance_id, current_date)
→ Returns: (success, message, distributions[])

# Calculate all funds in batch
calculate_batch_all_funds(batch_id, performance_data, current_date)
→ Returns: (success, message, summary{})

# Live weekly update (no performance needed)
calculate_live_weekly_update(batch_id, fund_name, current_date)
→ Returns: (success, message, weekly_data{})
```

---

## 📦 New Files & Structure

```
app/
├── Batch/
│   ├── fund.py                 # NEW: Fund & FundPerformance models
│   ├── fund_controllers.py      # NEW: Fund management controllers
│   ├── fund_routes.py           # NEW: Fund API endpoints
│   └── ...
│
├── logic/
│   └── pro_rata_service.py      # UPDATED: Multi-fund logic
│
├── utils/
│   ├── excel_handler.py         # NEW: Excel parsing & upload
│   ├── pdf_generator.py         # NEW: PDF statement generation
│   └── ...
│
└── Performance/
    ├── model.py                 # UPDATED: Fund-aware
    ├── pro_rata_distribution.py # UPDATED: Fund-aware
    └── ...
```

---

## 🛠️ Setup & Installation

### 1. Install New Dependencies
```bash
pip install reportlab openpyxl
```

Or update all:
```bash
pip install -r requirements.txt
```

### 2. Update Database Schema
```bash
python
>>> from main import app
>>> with app.app_context():
...     from app.database.database import db
...     db.drop_all()  # WARNING: Deletes existing data
...     db.create_all()
>>> exit()
```

### 3. Verify New Routes
```bash
# Start server
python main.py

# Test new endpoints (with valid JWT token)
curl http://localhost:5000/api/v1/batches/1/funds \
  -H "Authorization: Bearer <token>"
```

---

## 📈 Complete Workflow Example

### Phase 1: Create Batch
```bash
POST /api/v1/batches
{
    "batch_name": "Q1-2026-OFFSHORE",
    "certificate_number": "CERT-Q1-001",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30
}
→ Batch ID: 1
```

### Phase 2: Upload Investors (Excel)
```bash
POST /api/v1/batches/1/upload-excel
[Upload file with 12 investors]
→ Creates:
   - Fund: Axiom (7 investors, $350k)
   - Fund: Atium (5 investors, $250k)
```

### Phase 3: Record Performance
```bash
POST /api/v1/batches/1/funds/Axiom/performance
{"gross_profit": 100000, "transaction_costs": 5000}

POST /api/v1/batches/1/funds/Atium/performance
{"gross_profit": 75000, "transaction_costs": 2500}
```

### Phase 4: Calculate Distributions
```bash
POST /api/v1/batches/1/calculate-all-funds
{
    "performance_data": {
        "Axiom": 1,
        "Atium": 2
    }
}
→ Creates 12 ProRataDistribution records
```

### Phase 5: Get Summary
```bash
GET /api/v1/batches/1/summary
→ Shows all funds, capital, and distributed amounts
```

### Phase 6: Generate Report
```bash
GET /api/v1/batches/1/report/pdf?download=true
→ Downloads PDF with fund breakdown and investor details
```

---

## ⚠️ Important Notes

1. **Fund Creation**: Funds are created automatically during Excel upload if they don't exist
2. **Live Calculations**: All calculations use current_date for live accrual (not fixed batch duration)
3. **Fund Independence**: Each fund can have performance recorded independently
4. **Decimal Precision**: All financial calculations use `Decimal` type (4 decimal places for percentages, 2 for amounts)
5. **Weekly Triggers**: Use `/weekly-update` endpoint for real-time positions without performance data
6. **Backward Compatibility**: `ProRataCalculationService` alias maintained for existing code

---

## 🎓 API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/batches/{id}/funds` | GET | List all funds in batch |
| `/batches/{id}/funds/{name}` | GET | Get fund details & summary |
| `/batches/{id}/upload-excel` | POST | Bulk upload investors from Excel |
| `/batches/{id}/funds/{name}/performance` | POST | Record fund performance |
| `/batches/{id}/funds/{name}/weekly-update` | GET | Get live weekly position |
| `/batches/{id}/calculate-all-funds` | POST | Calculate all fund distributions |
| `/batches/{id}/summary` | GET | Get comprehensive batch summary |
| `/batches/{id}/report/pdf` | GET | Generate PDF statement |

---

**Documentation Generated:** March 16, 2026  
**Version:** 2.0 - Multi-Fund Portfolio System
