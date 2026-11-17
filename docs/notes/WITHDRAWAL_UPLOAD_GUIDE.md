# Withdrawal Upload Guide

## Overview
The withdrawal upload feature allows you to bulk upload investor withdrawals using an Excel file. The system will create withdrawal records with "Approved" status and reconcile them against existing investments.

## Step 1: Prepare Your Withdrawal File

### Required Columns (Exact names required):
| Column Name | Type | Required | Example |
|---|---|---|---|
| `investor_name` | Text | ✅ Yes | John Smith |
| `internal_client_code` | Text | ✅ Yes | AXIOM-001 |
| `amount(usd)` | Number | ✅ Yes | 50000.00 |
| `fund_name` | Text | ✅ Yes | Axiom |
| `date_transferred` | Date | ✅ Yes | 2026-04-03 |

### Column Details:
- **investor_name**: Full name of the investor (matches investment records)
- **internal_client_code**: Unique investor code (e.g., AXIOM-001, ATIUM-007)
- **amount(usd)**: Withdrawal amount in USD (number, no currency symbols)
- **fund_name**: Name of the fund (Axiom, Atium, etc.)
- **date_transferred**: Date of withdrawal in YYYY-MM-DD format

## Step 2: Using the Template

A template file has been created at:
```
C:\Users\Dantez\Downloads\ofds\backend\Withdrawal_Statement.xlsx
```

This template includes:
- ✅ All 5 required columns with blue header
- ✅ Pre-populated data for all active investors
- ✅ Proper formatting (currency, dates)
- ✅ Ready to use or modify

## Step 3: Make Your Changes

You can:
1. **Keep all data** - Upload as-is to process all withdrawals
2. **Modify amounts** - Change the withdrawal amount per investor
3. **Add/Remove rows** - Add new withdrawals or remove rows you don't need
4. **Change dates** - Update withdrawal dates if needed

## Step 4: Upload to the System

### Via Web Interface:
1. Navigate to `/withdrawals` page
2. Click **"Upload Excel"** button (top right)
3. Select your withdrawal file (.xlsx, .xls, or .csv)
4. System will:
   - Validate all required columns
   - Create/update withdrawal records
   - Set status to "Approved"
   - Link to corresponding batches

### Validation Rules:
- ❌ Missing required columns → Upload rejected
- ❌ Fund name not found → Row skipped with error
- ❌ Invalid amount → Row skipped
- ❌ Invalid date format → Row skipped
- ✅ Existing withdrawal for same investor+fund+date → Updated
- ✅ New withdrawal → Created

### API Endpoint (Direct):
```bash
curl -X POST http://localhost:5000/api/v1/withdrawals/upload \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@Withdrawal_Statement.xlsx"
```

## Step 5: Review Results

After upload, you'll see:
- ✅ Number of withdrawals created
- ✅ Number of withdrawals updated
- ⚠️ Any errors or rows that failed
- 📊 Withdrawal list updates automatically

## Example Withdrawal Data

```
investor_name            internal_client_code  amount(usd)  fund_name  date_transferred
John Smith              AXIOM-001             50000.00     Axiom      2026-04-03
Jane Doe                AXIOM-002             50000.00     Axiom      2026-04-03
Michael Johnson         AXIOM-003             50000.00     Axiom      2026-04-03
Jennifer White          ATIUM-007             50000.00     Atium      2026-04-03
Andrew Harris           ATIUM-008             50000.00     Atium      2026-04-03
```

## Notes

- Withdrawal amounts should be actual values being withdrawn (can be partial or full)
- The system will track these in the EpochLedger for reconciliation
- Withdrawals are marked "Approved" automatically on upload
- Date format must be YYYY-MM-DD (e.g., 2026-04-03)
- Fund names must exactly match fund records in the system
- Each withdrawal is linked to the investor's corresponding batch

## Troubleshooting

| Issue | Solution |
|---|---|
| "Missing required columns" | Check that all 5 columns exist with exact names |
| "Fund not found" | Verify fund_name matches exactly (Axiom, Atium, etc.) |
| "Invalid amount" | Ensure amount is a number without currency symbol |
| "Invalid date" | Use YYYY-MM-DD format (e.g., 2026-04-03) |
| Duplicate withdrawals | System will update if investor+fund+date matches |

## Support

For issues or questions, check the withdrawal records or contact support with:
- Your withdrawal file
- Error messages received
- Number of rows in file
