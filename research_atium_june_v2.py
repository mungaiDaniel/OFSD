import json
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker

DATABASE_URI = "postgresql://postgres:username@localhost/offshow_dev"
engine = create_engine(DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError

# Find fund
res = session.execute(text("SELECT id FROM core_funds WHERE fund_name = 'Atium'")).fetchone()
if not res:
    print("Fund Atium not found")
    exit()
fund_id = res[0]

# Find run
run = session.execute(text(f"SELECT id, epoch_start, epoch_end, head_office_total, status FROM valuation_runs WHERE core_fund_id = {fund_id} AND epoch_end = '2026-06-30'")).fetchone()
if not run:
    print("Run not found")
    exit()
run_id = run[0]

# Find ledgers
ledgers = session.execute(text(f"SELECT id, internal_client_code, withdrawals, end_balance, current_hash, previous_hash, epoch_start, performance_rate, start_balance, deposits, fund_name, epoch_end FROM epoch_ledger WHERE fund_name = 'Atium' AND epoch_end = '2026-06-30' AND withdrawals > 0")).fetchall()

# Find statements
statements = session.execute(text(f"SELECT id, investor_id, withdrawals, closing_balance FROM statements WHERE valuation_run_id = {run_id} AND withdrawals > 0")).fetchall()

data = {
    "run": {
        "id": run[0],
        "epoch_start": run[1],
        "epoch_end": run[2],
        "head_office_total": run[3],
        "status": run[4]
    },
    "ledgers": [dict(zip(["id", "internal_client_code", "withdrawals", "end_balance", "current_hash", "previous_hash", "epoch_start", "performance_rate", "start_balance", "deposits", "fund_name", "epoch_end"], l)) for l in ledgers],
    "statements": [dict(zip(["id", "investor_id", "withdrawals", "closing_balance"], s)) for s in statements]
}

with open('research_atium_june_v2.json', 'w') as f:
    json.dump(data, f, default=decimal_default, indent=2)
print("Data saved to research_atium_june_v2.json")
session.close()
