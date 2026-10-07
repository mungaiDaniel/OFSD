from sqlalchemy import create_engine, text

engine = create_engine('postgresql://postgres:username@localhost/offshow_dev')
with engine.connect() as conn:
    print("INVESTMENTS (AXIOM-001):")
    res = conn.execute(text("SELECT id, batch_id, internal_client_code, fund_name, amount_deposited, date_deposited FROM investments WHERE internal_client_code = 'AXIOM-001' ORDER BY date_deposited ASC"))
    for row in res:
        print(dict(row._mapping))
        
    print("\nPRO RATA (AXIOM-001):")
    res = conn.execute(text("SELECT investment_id, batch_id, fund_name, profit_allocated, calculation_date FROM pro_rata_distributions WHERE internal_client_code = 'AXIOM-001' ORDER BY calculation_date ASC"))
    for row in res:
        print(dict(row._mapping))

    print("\nEPOCH LEDGER (AXIOM-001):")
    res = conn.execute(text("SELECT fund_name, epoch_start, epoch_end, start_balance, deposits, withdrawals, profit, end_balance FROM epoch_ledger WHERE internal_client_code = 'AXIOM-001' ORDER BY epoch_end ASC"))
    for row in res:
        print(dict(row._mapping))
