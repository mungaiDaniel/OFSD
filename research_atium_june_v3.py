import json
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine, text
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

# Find run ID 6
run = session.execute(text("SELECT id, core_fund_id, epoch_start, epoch_end, head_office_total FROM valuation_runs WHERE id = 6")).fetchone()
run_id = run[0]

# Find ledgers for this epoch with withdrawals
# Since withdrawals might have been added to an existing 0, we look for the 50000 specifically or just any withdrawal in that run.
ledgers = session.execute(text(f"SELECT id, internal_client_code, withdrawals, end_balance, current_hash, previous_hash, epoch_start, performance_rate, start_balance, deposits, fund_name, epoch_end FROM epoch_ledger WHERE fund_name = 'Atium' AND epoch_end = '{run[3]}'")).fetchall()

# Actually, let's just look for any ledger in June for Atium that has withdrawals > 0
ledgers_june = session.execute(text("SELECT id, internal_client_code, withdrawals, end_balance, current_hash, previous_hash, epoch_start, epoch_end, start_balance, deposits, performance_rate FROM epoch_ledger WHERE fund_name = 'Atium' AND epoch_end >= '2026-06-30' AND epoch_end < '2026-07-01' AND withdrawals > 0")).fetchall()

# Statements for run 6
statements_june = session.execute(text(f"SELECT id, investor_id, withdrawals, closing_balance FROM statements WHERE valuation_run_id = {run_id} AND withdrawals > 0")).fetchall()

data = {
    "run": dict(zip(["id", "core_fund_id", "epoch_start", "epoch_end", "head_office_total"], run)),
    "ledgers": [dict(zip(["id", "internal_client_code", "withdrawals", "end_balance", "current_hash", "previous_hash", "epoch_start", "epoch_end", "start_balance", "deposits", "performance_rate"], l)) for l in ledgers_june],
    "statements": [dict(zip(["id", "investor_id", "withdrawals", "closing_balance"], s)) for s in statements_june]
}

with open('research_atium_june_v3.json', 'w') as f:
    json.dump(data, f, default=decimal_default, indent=2)
session.close()
