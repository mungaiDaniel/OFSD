import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

start_date = datetime(2026, 8, 1)
end_date = datetime(2026, 8, 31)

cursor.execute("""
    SELECT internal_client_code, amount_deposited, date_deposited, fund_name, batch_id
    FROM investments
    WHERE (lower(fund_name) = 'axiom' OR fund_id = (SELECT id FROM core_funds WHERE lower(fund_name) = 'axiom'))
    AND date_deposited >= %s
    AND date_deposited <= %s
""", (start_date, end_date))

rows = cursor.fetchall()
print(f"Total August Axiom investments: {len(rows)}")
total = sum(row['amount_deposited'] for row in rows)
print(f"Total: {total}")

# Breakdown by batch
batches = {}
for row in rows:
    bid = row['batch_id']
    batches[bid] = batches.get(bid, 0) + row['amount_deposited']

print("\nBy Batch ID:")
for bid, amt in batches.items():
    print(f"  Batch {bid}: {amt}")

cursor.close()
conn.close()
