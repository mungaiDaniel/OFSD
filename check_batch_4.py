import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

cursor.execute("""
    SELECT internal_client_code, amount_deposited, date_deposited, fund_name
    FROM investments
    WHERE batch_id = 4
    ORDER BY date_deposited
""")

rows = cursor.fetchall()
for row in rows:
    print(f"Code: {row['internal_client_code']}, Amount: {row['amount_deposited']}, Date: {row['date_deposited']}")

cursor.close()
conn.close()
