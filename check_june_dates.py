import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from datetime import datetime, timezone
from flask import Flask
from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment
import config

app = Flask(__name__)
app.config.from_object(config.DevelopmentConfig)
db.init_app(app)

with app.app_context():
    axiom = CoreFund.query.filter(CoreFund.fund_name.ilike('Axiom')).first()
    start_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 6, 30, tzinfo=timezone.utc)
    
    invs = Investment.query.filter(Investment.fund_id == axiom.id).all()
    print(f"Total Axiom investments: {len(invs)}")
    june_count = 0
    for inv in invs:
        if inv.date_deposited and inv.date_deposited >= start_date and inv.date_deposited <= end_date:
            june_count += 1
            batch_date = inv.batch.date_deployed if inv.batch else None
            print(f"- {inv.internal_client_code}: deposited={inv.date_deposited}, batch={inv.batch.batch_name if inv.batch else 'None'}, batch_deployed={batch_date}")
    
    print(f"Total June investments: {june_count}")
