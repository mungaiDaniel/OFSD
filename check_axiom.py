from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment, EpochLedger
from flask import Flask
import os
from datetime import datetime
from decimal import Decimal

app = Flask(__name__)
# Assuming the DB path is here, let's double check if it exists or use relative
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/ofds.db'
db.init_app(app)

with app.app_context():
    axiom = CoreFund.query.filter(CoreFund.fund_name.ilike('Axiom')).first()
    if not axiom:
        print("Axiom fund not found")
    else:
        print(f"Axiom Fund ID: {axiom.id}")
        
        # Check May Valuations
        may_start = datetime(2026, 5, 1)
        may_end = datetime(2026, 5, 31)
        may_ledgers = EpochLedger.query.filter(
            EpochLedger.fund_name.ilike('Axiom'),
            EpochLedger.epoch_end == may_end
        ).all()
        
        may_total = sum(Decimal(str(l.end_balance)) for l in may_ledgers)
        print(f"May Valuations Total: {may_total}")
        print(f"Count of May records: {len(may_ledgers)}")
        
        # Check June Investments
        june_start = datetime(2026, 6, 1)
        june_end = datetime(2026, 6, 30)
        june_investments = Investment.query.filter(
            Investment.fund_id == axiom.id,
            Investment.date_deposited >= june_start,
            Investment.date_deposited <= june_end
        ).all()
        
        june_principal = sum(Decimal(str(i.amount_deposited)) for i in june_investments)
        print(f"June Principal Total: {june_principal}")
        print(f"Count of June investments: {len(june_investments)}")
        for inv in june_investments:
             print(f"  - {inv.internal_client_code}: {inv.amount_deposited} on {inv.date_deposited}")

        # Check if any June Valuations already exist
        june_ledgers = EpochLedger.query.filter(
            EpochLedger.fund_name.ilike('Axiom'),
            EpochLedger.epoch_end == june_end
        ).all()
        print(f"June Valuations already exist? {len(june_ledgers) > 0}")
