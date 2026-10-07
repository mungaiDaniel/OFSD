import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
from datetime import datetime

conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

# May end date
may_end = datetime(2026, 5, 31)

cursor.execute("""
    SELECT internal_client_code, fund_name, epoch_end, end_balance
    FROM epoch_ledger
    WHERE lower(fund_name) = 'axiom'
    AND epoch_end = %s
""", (may_end,))

may_rows = cursor.fetchall()
print(f"Total May Axiom records: {len(may_rows)}")
may_total = sum(row['end_balance'] for row in may_rows)
print(f"May Total: {may_total}")

cursor.execute("SELECT count(*) as count FROM investments WHERE lower(fund_name) = 'axiom' OR fund_id = (SELECT id FROM core_funds WHERE lower(fund_name) = 'axiom')")
print(f"Total Axiom investments in DB: {cursor.fetchone()['count']}")

cursor.close()
conn.close()
