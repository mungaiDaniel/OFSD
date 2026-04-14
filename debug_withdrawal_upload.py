#!/usr/bin/env python
"""
Comprehensive withdrawal upload debugging and testing script.
Tests the entire withdrawal flow: file reading, backend processing, and database save.
"""

import sys
import pandas as pd
from datetime import datetime
from decimal import Decimal

# Test 1: File Reading
print("=" * 70)
print("TEST 1: File Reading & Validation")
print("=" * 70)

file_path = "Withdrawal_Statement.xlsx"
try:
    df = pd.read_excel(file_path)
    print(f"✅ File read successfully")
    print(f"   Shape: {df.shape} (rows, columns)")
    print(f"   Columns: {df.columns.tolist()}")
    df_clean = df.copy()
except Exception as e:
    print(f"❌ Failed to read file: {e}")
    sys.exit(1)

# Test 2: Column Normalization
print("\n" + "=" * 70)
print("TEST 2: Column Normalization")
print("=" * 70)

df_clean.columns = df_clean.columns.str.lower().str.strip()
print(f"✅ Columns normalized: {df_clean.columns.tolist()}")

# Test 3: Column Mapping
print("\n" + "=" * 70)
print("TEST 3: Column Mapping")
print("=" * 70)

column_mapping = {
    'internal_client_code': 'internal_client_code',
    'amount(usd)': 'amount',
    'amount': 'amount',
    'fund_name': 'fund_name',
    'date_transferred': 'date_withdrawn',
    'date_withdrawn': 'date_withdrawn',
    'investor_name': 'investor_name',
    'status': 'status',
    'note': 'note',
}

df_clean = df_clean.rename(columns={k: v for k, v in column_mapping.items() if k in df_clean.columns})
print(f"✅ Mapping applied. Columns: {df_clean.columns.tolist()}")

# Test 4: Required Columns Check
print("\n" + "=" * 70)
print("TEST 4: Required Columns Validation")
print("=" * 70)

required_columns = ['internal_client_code', 'amount', 'fund_name', 'date_withdrawn']
missing = [c for c in required_columns if c not in df_clean.columns]

if missing:
    print(f"❌ Missing required columns: {missing}")
    sys.exit(1)
else:
    print(f"✅ All required columns present: {required_columns}")

# Test 5: Data Cleaning
print("\n" + "=" * 70)
print("TEST 5: Data Cleaning & Dropna")
print("=" * 70)

before_rows = len(df_clean)
df_clean = df_clean.dropna(subset=required_columns)
after_rows = len(df_clean)

print(f"✅ Rows before cleanup: {before_rows}")
print(f"✅ Rows after cleanup: {after_rows}")
print(f"✅ Dropped rows: {before_rows - after_rows}")

# Test 6: Row Processing & Parsing
print("\n" + "=" * 70)
print("TEST 6: Individual Row Processing")
print("=" * 70)

successful_rows = 0
failed_rows = 0
errors = []

for idx, row in df_clean.iterrows():
    try:
        # Required fields
        internal_code = str(row['internal_client_code']).strip()
        fund_name = str(row['fund_name']).strip()
        amount = Decimal(str(row['amount']))
        date_withdrawn = row['date_withdrawn']
        
        # Parse date if string
        if isinstance(date_withdrawn, str):
            for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    date_withdrawn = datetime.strptime(date_withdrawn, date_format)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Invalid date format: {date_withdrawn}")
        
        # Convert pandas Timestamp to datetime
        if hasattr(date_withdrawn, 'to_pydatetime'):
            date_withdrawn = date_withdrawn.to_pydatetime()
        
        # Optional fields
        investor_name = str(row.get('investor_name', '')).strip() if 'investor_name' in row else ''
        status = str(row.get('status', 'Pending')).strip().capitalize() if 'status' in row else 'Pending'
        note = str(row.get('note', '')).strip() if 'note' in row else None
        
        # Validate status
        if status not in ('Pending', 'Approved', 'Rejected'):
            status = 'Pending'
        
        successful_rows += 1
        
        if successful_rows <= 3:  # Show details for first 3 rows
            print(f"\n  ✅ Row {idx + 2}:")
            print(f"     - internal_client_code: {internal_code}")
            print(f"     - investor_name: {investor_name}")
            print(f"     - fund_name: {fund_name}")
            print(f"     - amount: ${amount:,.2f}")
            print(f"     - date_withdrawn: {date_withdrawn.strftime('%Y-%m-%d')}")
            print(f"     - status: {status}")
            print(f"     - note: {note or '(empty)'}")
    
    except Exception as e:
        failed_rows += 1
        errors.append(f"Row {idx + 2}: {str(e)}")

print(f"\n✅ Processing complete:")
print(f"   Successful rows: {successful_rows}")
print(f"   Failed rows: {failed_rows}")

if errors:
    print(f"\n❌ Errors:")
    for err in errors:
        print(f"   - {err}")
else:
    print(f"\n✅ No errors encountered!")

# Test 7: Summary Statistics
print("\n" + "=" * 70)
print("TEST 7: Summary Statistics")
print("=" * 70)

total_amount = df_clean['amount'].sum()
unique_funds = df_clean['fund_name'].nunique()
unique_codes = df_clean['internal_client_code'].nunique()

print(f"✅ Total withdrawal amount: ${total_amount:,.2f}")
print(f"✅ Unique funds: {unique_funds}")
print(f"✅ Unique investors: {unique_codes}")
print(f"✅ Total rows to process: {successful_rows}")

# Final Status
print("\n" + "=" * 70)
print("FINAL STATUS")
print("=" * 70)

if failed_rows == 0:
    print("✅ FILE IS READY FOR UPLOAD")
    print(f"   - {successful_rows} withdrawals will be created/updated")
    print(f"   - ${total_amount:,.2f} total amount")
else:
    print(f"⚠️  PARTIAL SUCCESS: {successful_rows} rows ready, {failed_rows} errors")
