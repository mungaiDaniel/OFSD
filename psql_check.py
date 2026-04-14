import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal

# Connection string manually derived from config
conn = psycopg2.connect("postgresql://postgres:username@localhost/offshore")
cursor = conn.cursor(cursor_factory=RealDictCursor)

cursor.execute("SELECT id FROM core_funds WHERE lower(fund_name) = 'axiom'")
axiom = cursor.fetchone()

if axiom:
    axiom_id = axiom['id']
    cursor.execute("""
        SELECT internal_client_code, amount_deposited, date_deposited, batch_id
        FROM investments
        WHERE fund_id = %s
    """, (axiom_id,))
    
    investments = cursor.fetchall()
    print(f"Total Axiom investments: {len(investments)}")
    
    june_count = 0
    june_principal = Decimal("0")
    for inv in investments:
        dd = inv['date_deposited']
        if dd and dd.year == 2026 and dd.month == 6:
            june_count += 1
            june_principal += inv['amount_deposited']
            
            # get batch deployment date
            cursor.execute("SELECT date_deployed FROM batches WHERE id = %s", (inv['batch_id'],))
            batch = cursor.fetchone()
            b_deployed = batch['date_deployed'] if batch else None
            
            print(f"- {inv['internal_client_code']}: deposited={dd}, batch_deployed={b_deployed}, amount={inv['amount_deposited']}")
            
    print(f"Total June investments: {june_count}, Total Principal: {june_principal}")
else:
    print("Axiom not found.")

cursor.close()
conn.close()
