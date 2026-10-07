import pandas as pd
import os
from datetime import datetime

# Test reading the withdrawal file we created
file_path = "Withdrawal_Statement.xlsx"

if os.path.exists(file_path):
    print(f"✅ File exists: {file_path}")
    
    # Read without header to see legend row
    df_full = pd.read_excel(file_path, sheet_name='Withdrawals')
    print(f"\n📋 Raw DataFrame shape: {df_full.shape}")
    print(f"📋 Columns: {df_full.columns.tolist()}")
    print(f"\n📋 First 3 rows:")
    print(df_full.head(3))
    
    # Check for required columns
    required = ['internal_client_code', 'amount', 'fund_name', 'date_withdrawn']
    missing = [c for c in required if c not in df_full.columns]
    
    if missing:
        print(f"\n❌ Missing required columns: {missing}")
    else:
        print(f"\n✅ All required columns present")
        print(f"✅ Total rows with data: {len(df_full) - 2}")  # Subtract header and legend
        print(f"✅ File is ready for upload!")
else:
    print(f"❌ File not found: {file_path}")
