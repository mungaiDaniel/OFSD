# Multi-Fund Implementation Checklist

## ✅ Pre-Implementation

- [ ] Backup existing database
- [ ] Review MULTI_FUND_REFACTORING_GUIDE.md thoroughly
- [ ] Communicate changes to frontend team
- [ ] Prepare Excel template for investors

## 📦 Installation Steps

### Step 1: Pull Code Changes
```bash
# All new files have been created:
# - app/Batch/fund.py              (Fund & FundPerformance models)
# - app/Batch/fund_controllers.py  (Fund management controllers)
# - app/Batch/fund_routes.py       (Fund API endpoints)
# - app/utils/excel_handler.py     (Excel upload utility)
# - app/utils/pdf_generator.py     (PDF generation utility)

# Updated files:
# - app/Investments/model.py       (Added fund_name, internal_client_code)
# - app/Performance/model.py       (Added fund_name)
# - app/Performance/pro_rata_distribution.py (Fund-aware)
# - app/logic/pro_rata_service.py  (Multi-fund calculation logic)
# - main.py                        (Register new blueprint)
# - requirements.txt               (Added reportlab)
```

### Step 2: Install Dependencies
```bash
pip install -U -r requirements.txt
```

### Step 3: Create Database & Schema
```bash
cd c:\Users\Dantez\Documents\ofds\backend

# Activate virtual environment
& venv\Scripts\Activate.ps1

# Drop old tables and create new schema
python
```

Inside Python:
```python
from main import app
from app.database.database import db

with app.app_context():
    # BACKUP FIRST - This deletes tables
    # Export data if you have existing batches
    
    # Drop all
    db.drop_all()
    
    # Create new schema with Fund and FundPerformance models
    db.create_all()
    
    print("Database schema updated successfully")
```

Exit Python:
```
exit()
```

### Step 4: Verify Installation
```bash
# Start server
python main.py
```

Test with curl (get token first):
```bash
# 1. Create user
curl -X POST http://localhost:5000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Admin",
    "email": "admin@test.com",
    "password": "test"
  }'

# 2. Login
curl -X POST http://localhost:5000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "test"
  }'

# Save the access_token from response
TOKEN="<access_token>"

# 3. Create batch
curl -X POST http://localhost:5000/api/v1/batches \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "batch_name": "TEST-BATCH",
    "certificate_number": "CERT-TEST-001",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30
  }'

# 4. Test new funds endpoint
curl http://localhost:5000/api/v1/batches/1/funds \
  -H "Authorization: Bearer $TOKEN"
```

## 📋 Excel Template Setup

### Create Excel File Format
```
Column Headers (A-F):
A: investor_name
B: investor_email
C: internal_client_code
D: amount(usd)
E: fund
F: date_transferred

Sample Data (Row 2+):
John Doe        | john@example.com    | AXIOM-001  | 50000.00  | Axiom | 2026-03-10
Jane Smith      | jane@example.com    | AXIOM-002  | 40000.00  | Axiom | 2026-03-01
Bob Wilson      | bob@example.com     | AXIOM-003  | 30000.00  | Axiom | 2026-03-05
...
Alice Johnson   | alice@example.com   | ATIUM-008  | 75000.00  | Atium | 2026-03-05
Charlie Brown   | charlie@example.com | ATIUM-009  | 60000.00  | Atium | 2026-03-08
...
```

### Save as Excel 2016+ (.xlsx)

## 🚀 First Workflow Test

### 1. Create Batch
```bash
POST /api/v1/batches
{
    "batch_name": "DEMO-BATCH",
    "certificate_number": "CERT-DEMO-001",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30
}
```
Save the batch ID (e.g., 1)

### 2. Upload Excel
```bash
POST /api/v1/batches/1/upload-excel
[Select Excel file with 12 investors]
```

Verify response shows 2 funds created:
- Axiom: 7 investors
- Atium: 5 investors

### 3. Record Performance
```bash
POST /api/v1/batches/1/funds/Axiom/performance
{
    "gross_profit": 100000.00,
    "transaction_costs": 5000.00,
    "reporting_period": "MONTHLY"
}

POST /api/v1/batches/1/funds/Atium/performance
{
    "gross_profit": 75000.00,
    "transaction_costs": 2500.00,
    "reporting_period": "MONTHLY"
}
```

### 4. Calculate Distributions
```bash
POST /api/v1/batches/1/calculate-all-funds
{
    "performance_data": {
        "Axiom": 1,
        "Atium": 2
    }
}
```

### 5. Verify Results
```bash
GET /api/v1/batches/1/funds
GET /api/v1/batches/1/summary
GET /api/v1/batches/1/report/pdf?download=true
```

## 🧪 Testing Checklist

### Fund Management
- [ ] Create batch successfully
- [ ] List funds in batch
- [ ] Get fund details with investments

### Excel Upload
- [ ] Upload file with proper format
- [ ] Verify funds auto-created
- [ ] Verify investor counts correct
- [ ] Get fund summaries after upload

### Performance Recording
- [ ] Record Axiom performance
- [ ] Record Atium performance independently
- [ ] Verify cumulative profit calculations
- [ ] Get fund performance history

### Pro-Rata Calculations
- [ ] Calculate distributions for single fund
- [ ] Calculate distributions for all funds
- [ ] Verify weighted capital calculations
- [ ] Verify profit share percentages sum to 100%
- [ ] Verify allocated profits sum to net profit

### Live Weekly Updates
- [ ] Get weekly update for Axiom
- [ ] Get weekly update for Atium
- [ ] Verify days_active calculation
- [ ] Check investor count and capital

### PDF Reporting
- [ ] Generate PDF report
- [ ] Verify funds are grouped correctly
- [ ] Verify investor codes displayed
- [ ] Verify profit allocations shown

### API Edge Cases
- [ ] Try to record performance for non-existent fund
- [ ] Try to upload Excel to non-existent batch
- [ ] Try calculations with no performance data
- [ ] Try calculations with missing fund performance

## 🔄 Migration from Old System

If you have existing batch data:

### Step 1: Export Data
```bash
# Export old Users, Batches, Investments, Performance
pg_dump -U postgres offshow-dev > backup.sql
```

### Step 2: Create Data Migration Script
```python
# Create app/migrations/migrate_to_multifund.py
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.Batch.fund import Fund
from app.database.database import db

# For each batch:
for batch in Batch.query.all():
    # Create default fund for existing investments
    fund = Fund(
        batch_id=batch.id,
        fund_name='Default',
        certificate_number=batch.certificate_number,
        date_deployed=batch.date_deployed,
        duration_days=batch.duration_days
    )
    db.session.add(fund)
    db.session.flush()
    
    # Link existing investments to fund
    for inv in batch.investments:
        inv.fund_name = 'Default'
        inv.fund_id = fund.id
        inv.internal_client_code = f'DEFAULT-{inv.id:03d}'  # Auto-generate
    
    # Update fund total_capital
    fund.total_capital = sum(inv.amount_deposited for inv in batch.investments)

db.session.commit()
```

### Step 3: Run Migration
```bash
python
>>> exec(open('app/migrations/migrate_to_multifund.py').read())
```

## 📞 Support & Troubleshooting

### Import Errors
**Problem:** `ImportError: cannot import name 'Fund'`
- Check that `app/Batch/fund.py` exists
- Verify `from app.Batch.fund import Fund` in imports
- Ensure all files are created

### Database Errors
**Problem:** `sqlalchemy.exc.OperationalError`
- Verify PostgreSQL is running
- Check connection string in `config.py`
- Ensure database `offshow-dev` exists

### Excel Upload Fails
**Problem:** Excel file not recognized
- Verify file is `.xlsx` format (not `.xls` or `.csv`)
- Check required columns exist
- Verify numeric columns contain numbers (not text)

### Missing Fund in Upload
**Problem:** Fund not auto-created during upload
- Check Excel 'fund' column spelling (case-sensitive for auto-assign)
- Verify Excel row has all required fields
- Check for duplicate internal_client_code values

### PDF Generation Error
**Problem:** PDF fails to generate
- Verify `reportlab` is installed: `pip install reportlab`
- Check batch has distributions before generating PDF
- Ensure file permissions allow writing to reports/ directory

### Distribution Mismatch
**Problem:** Profit allocated doesn't sum correctly
- Check all investors assigned to fund
- Verify weighted capital calculations
- Ensure performance_data mapping is correct

## 📚 Documentation Files

1. **PROJECT_WALKTHROUGH.md** - Original single-fund architecture
2. **MULTI_FUND_REFACTORING_GUIDE.md** - Complete multi-fund documentation
3. **IMPLEMENTATION_CHECKLIST.md** - This file

## 🎯 Next Steps

After successful setup:

1. **Train Frontend Team** on new endpoints
2. **Update UI** to show fund selection/management
3. **Create Excel Import Wizard** for UX
4. **Schedule Weekly Reports** generation via cron
5. **Monitor Performance** with error logging
6. **Establish Backup Plan** for production deployment

---

**Checklist Version:** 1.0  
**Last Updated:** March 16, 2026
