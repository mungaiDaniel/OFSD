import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

start_date = datetime(2026, 8, 1)
end_date = datetime(2026, 8, 31)

print("Searching ONLY by fund_name='axiom'...")
cursor.execute("""
    SELECT internal_client_code, amount_deposited, date_deposited, fund_name
    FROM investments
    WHERE lower(fund_name) = 'axiom'
    AND date_deposited >= %s
    AND date_deposited <= %s
""", (start_date, end_date))

rows = cursor.fetchall()
print(f"Total: {len(rows)}, Sum: {sum(row['amount_deposited'] for row in rows)}")

print("\nSearching by fund_id for Axiom...")
cursor.execute("SELECT id FROM core_funds WHERE lower(fund_name) = 'axiom'")
axiom_id = cursor.fetchone()['id']

cursor.execute("""
    SELECT internal_client_code, amount_deposited, date_deposited, fund_name
    FROM investments
    WHERE fund_id = %s
    AND date_deposited >= %s
    AND date_deposited <= %s
""", (axiom_id, start_date, end_date))

rows_by_id = cursor.fetchall()
print(f"Total: {len(rows_by_id)}, Sum: {sum(row['amount_deposited'] for row in rows_by_id)}")

# Check overlap
codes_by_name = {row['internal_client_code'] for row in rows}
codes_by_id = {row['internal_client_code'] for row in rows_by_id}

print(f"\nCodes in Name only: {codes_by_name - codes_by_id}")
print(f"Codes in ID only: {codes_by_id - codes_by_name}")

for row in rows_by_id:
    if row['internal_client_code'] in (codes_by_id - codes_by_name):
        print(f"  ID-only deposit: {row['internal_client_code']}, Amount: {row['amount_deposited']}, Name in DB: {row['fund_name']}")

cursor.close()
conn.close()
