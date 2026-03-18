# Withdrawal Fund ID Migration - Complete Guide

## Overview
This guide walks you through syncing your PostgreSQL `withdrawals` table with your SQLAlchemy models. The issue was that the `Withdrawal` model defined a `fund_id` column, but the PostgreSQL table didn't have it yet.

---

## What Was Changed

### 1. **Withdrawal Model** (`backend/app/Investments/model.py`)
✅ **Added:** Fund and Batch relationships
```python
# Relationships
fund = db.relationship('CoreFund', backref='withdrawals')
batch = db.relationship('Batch', backref='withdrawals')
```

**Impact:** You can now access `withdrawal.fund.fund_name` to get the fund name from the related CoreFund object.

---

### 2. **GET /withdrawals Endpoint** (`backend/app/Investments/route.py`)
✅ **Updated:** Now returns fund information via the relationship
```python
"fund_name": w.fund.fund_name if w.fund else w.fund_name,
```

**Additional Fields in Response:**
- `approved_at` - Timestamp when withdrawal was approved
- `note` - Optional notes on the withdrawal

---

### 3. **Migration Script** (`backend/migrate_withdrawal_fund_id.py`)
✅ **Created:** Automated migration script that:
- ✓ Adds `fund_id` column to `withdrawals` table
- ✓ Sets default value of 1 (Axiom Fund) for existing rows
- ✓ Adds NOT NULL constraint after data is populated
- ✓ Adds FOREIGN KEY constraint to `core_funds(id)`
- ✓ Creates index: `ix_withdrawals_code_fund_date` on (internal_client_code, fund_id, date_withdrawn)
- ✓ Verifies the table structure after migration

---

## How to Run the Migration

### Step 1: Backup Your Database (IMPORTANT!)
```bash
# PostgreSQL backup
pg_dump ofds_db > ofds_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Run the Migration Script
```bash
cd backend

# Activate virtual environment (if not already active)
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# Run migration
python migrate_withdrawal_fund_id.py
```

**Expected Output:**
```
================================================================================
Migration: Add fund_id column to withdrawals table
================================================================================

[1] Adding fund_id column...
    ✓ fund_id column added

[2] Setting default values for existing rows...
    ✓ Default values set (fund_id = 1 for all existing rows)

[3] Adding NOT NULL constraint...
    ✓ NOT NULL constraint applied

[4] Adding foreign key constraint...
    ✓ Foreign key constraint added

[5] Adding/ensuring index...
    ✓ Index created/verified

================================================================================
✓ Migration completed successfully!
================================================================================

[VERIFICATION] Checking withdrawals table structure...

Columns in withdrawals table:
Column                    Type            Nullable
--------------------------------------------------
id                        integer         NO
internal_client_code      character       NO
fund_id                   integer         NO
fund_name                 character       YES
amount                    numeric         NO
date_withdrawn            timestamp       NO
status                    character       NO
approved_at               timestamp       YES
note                      character       YES
batch_id                  integer         YES

✓ Verification complete!
```

### Step 3: Restart Backend
```bash
# Kill previous instance (Ctrl+C)

# Start fresh
python main.py
```

---

## API Usage - Frontend Reference

### Creating a Withdrawal
```javascript
// POST /api/v1/withdrawals
const response = await fetch('/api/v1/withdrawals', {
  method: 'POST',
  headers: { 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    client_id: 'AXIOM-001',        // internal_client_code
    fund_id: 1,                    // Required (Integer)
    amount: 5000.00,               // Required (Decimal)
    status: 'Pending'              // Optional: 'Pending'|'Approved'|'Rejected'
  })
});
```

### Listing Withdrawals
```javascript
// GET /api/v1/withdrawals?status=Pending
const response = await fetch('/api/v1/withdrawals?status=Pending', {
  headers: { 'Authorization': `Bearer ${token}` }
});

// Response:
{
  "status": 200,
  "message": "Withdrawals retrieved",
  "data": [
    {
      "id": 1,
      "client_id": "AXIOM-001",
      "fund_id": 1,
      "fund_name": "Axiom",           // From CoreFund relationship
      "amount": 5000.00,
      "status": "Pending",
      "date_withdrawn": "2026-03-17T14:30:00",
      "approved_at": null,
      "note": null
    }
  ]
}
```

### Updating a Withdrawal Status
```javascript
// PATCH /api/v1/withdrawals/<id>
const response = await fetch('/api/v1/withdrawals/1', {
  method: 'PATCH',
  headers: { 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    status: 'Approved'  // or 'Rejected'
  })
});
```

---

## Frontend Status

✅ **WithdrawalManager.js** - Already correctly implemented!
- ✓ Sends `fund_id` in the withdrawal creation request
- ✓ Receives and displays the fund information in the table
- ✓ Dropdown selector for fund selection

**No frontend changes needed!**

---

## Verification Checklist

After running the migration, verify everything works:

- [ ] Migration runs without errors
- [ ] POST `/api/v1/withdrawals` creates withdrawals with fund_id
- [ ] GET `/api/v1/withdrawals` returns fund_name from CoreFund relationship
- [ ] PATCH `/api/v1/withdrawals/<id>` updates status correctly
- [ ] WithdrawalManager.js in frontend shows fund names correctly
- [ ] No "column withdrawals.fund_id does not exist" errors

---

## Troubleshooting

### Error: "Foreign key constraint already exists"
If the FK constraint already exists, the migration will skip it gracefully.

### Error: "Column already exists"
The migration uses `ADD COLUMN IF NOT EXISTS`, so it's safe to run multiple times.

### Error: "Relationship load failed"
If you get errors accessing `w.fund.fund_name`, ensure:
1. Migration was run successfully (fund_id column exists)
2. CoreFund records exist (Axiom, Atium)
3. fund_id values in withdrawals table reference valid core_funds IDs

### Check Migration Status
```bash
# In PostgreSQL, verify column exists:
psql -U <user> -d ofds_db -c "\d withdrawals"

# Should show:
#  fund_id | integer | not null
```

---

## Summary of Files Modified

| File | Change | Impact |
|------|--------|--------|
| `backend/app/Investments/model.py` | Added fund & batch relationships | Can now access `withdrawal.fund` |
| `backend/app/Investments/route.py` | Updated GET /withdrawals response | Returns fund_name via relationship |
| `backend/migrate_withdrawal_fund_id.py` | **NEW** Migration script | Syncs PostgreSQL with models |
| `frontend/src/pages/WithdrawalManager.js` | No changes needed | Already working correctly |

---

## Next Steps

After migration:
1. Run backend: `python main.py`
2. Run frontend: `npm start`
3. Test withdrawal creation in WithdrawalManager page
4. Verify funds are displayed correctly in the withdrawal table

**Ready to sync!** Let me know if you hit any issues during migration. 🚀
