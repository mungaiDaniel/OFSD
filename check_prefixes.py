import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

start_date = datetime(2026, 8, 1)
end_date = datetime(2026, 8, 31)

cursor.execute("""
    SELECT internal_client_code, amount_deposited, fund_name
    FROM investments
    WHERE (lower(fund_name) = 'axiom' OR fund_id = (SELECT id FROM core_funds WHERE lower(fund_name) = 'axiom'))
    AND date_deposited >= %s
    AND date_deposited <= %s
""", (start_date, end_date))

rows = cursor.fetchall()
axiom_sum = 0
aditum_sum = 0

for row in rows:
    code = row['internal_client_code']
    if code.startswith('AXIOM'):
        axiom_sum += row['amount_deposited']
    elif code.startswith('ADITUM'):
        aditum_sum += row['amount_deposited']
    else:
        print(f"Unknown code prefix: {code}")

print(f"Total: {sum(row['amount_deposited'] for row in rows)}")
print(f"AXIOM prefix sum: {axiom_sum}")
print(f"ADITUM prefix sum: {aditum_sum}")

target_august = 1972000.00
print(f"\nTarget August: {target_august}")
print(f"Difference (Total - Target): {sum(row['amount_deposited'] for row in rows) - target_august}")
