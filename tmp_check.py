import sys
sys.path.insert(0, '.')
from main import app
from app.database.database import db
from app.Investments.model import Investment
from app.Batch.core_fund import CoreFund
from sqlalchemy import func

with app.app_context():
    core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == 'atium').first()
    print("--- Investments in DB for Atium ---")
    invs = db.session.query(Investment).filter(Investment.fund_id == core.id).all()
    for inv in invs:
        print(f"id={inv.id} code={inv.internal_client_code} batch={inv.batch_id} deposited={inv.date_deposited}")

    print("\n--- John Smith Check ---")
    # In earlier runs, we assumed ATIUM-010 is John Smith maybe? Let's print any that match name if there's no Investor base table.
    # Actually wait we can just check if there's an ATIUM-010 or similar missing.
    # What was the problem: ATIUM has only 3 rows instead of 4.
    pass

