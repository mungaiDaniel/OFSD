from sqlalchemy import create_engine, text
import json

engine = create_engine('postgresql://postgres:username@localhost/offshow_dev')
with engine.connect() as conn:
    print("ALL EPOCHS:")
    res = conn.execute(text("SELECT fund_name, epoch_end, start_balance, end_balance FROM epoch_ledger ORDER BY epoch_end DESC LIMIT 20"))
    for row in res:
        print(dict(row._mapping))
    print("VALUATION RUNS:")
    res = conn.execute(text("SELECT id, core_fund_id, epoch_start, epoch_end, status FROM valuation_runs ORDER BY epoch_end DESC LIMIT 5"))
    for row in res:
        print(dict(row._mapping))
