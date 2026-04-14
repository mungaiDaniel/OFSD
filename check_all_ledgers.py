import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal

conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

cursor.execute("""
    SELECT distinct fund_name, epoch_end, sum(end_balance) as total
    FROM epoch_ledger
    WHERE lower(fund_name) like 'axiom%'
    GROUP BY fund_name, epoch_end
    ORDER BY epoch_end desc
""")

rows = cursor.fetchall()
for row in rows:
    print(f"Fund: {row['fund_name']}, End: {row['epoch_end']}, Total: {row['total']}")

cursor.close()
conn.close()
