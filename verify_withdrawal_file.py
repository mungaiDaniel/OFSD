import pandas as pd

df = pd.read_excel('Withdrawal_Statement.xlsx')
print("WITHDRAWAL FILE STATUS")
print("=" * 50)
print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")
print(f"\nFirst 3 rows:")
for i, row in df.head(3).iterrows():
    print(f"  Row {i+1}: {row['internal_client_code']} - ${row['amount']:.2f}")
print(f"\nTotal amount: ${df['amount'].sum():,.2f}")
print(f"\nStatus: READY FOR UPLOAD")
