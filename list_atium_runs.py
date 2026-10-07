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

# Find fund
res = session.execute(text("SELECT id FROM core_funds WHERE fund_name = 'Atium'")).fetchone()
fund_id = res[0]

# List all runs
runs = session.execute(text(f"SELECT id, epoch_start, epoch_end, head_office_total, status FROM valuation_runs WHERE core_fund_id = {fund_id}")).fetchall()
data = [dict(zip(["id", "epoch_start", "epoch_end", "head_office_total", "status"], r)) for r in runs]

with open('atium_runs.json', 'w') as f:
    json.dump(data, f, default=decimal_default, indent=2)
session.close()
