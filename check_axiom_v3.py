from flask import Flask
from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Performance.model import Performance
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from datetime import datetime
from decimal import Decimal

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///c:/Users/Dantez/Downloads/ofds/backend/instance/ofds.db'
db.init_app(app)

with app.app_context():
    axiom = CoreFund.query.filter(CoreFund.fund_name.ilike('Axiom')).first()
    if not axiom:
        print("Axiom fund not found")
    else:
        print(f"Axiom Fund ID: {axiom.id}")
        
        may_end = datetime(2026, 5, 31)
        may_ledgers = EpochLedger.query.filter(
            EpochLedger.fund_name.ilike('Axiom'),
            EpochLedger.epoch_end == may_end
        ).all()
        
        may_total = sum(Decimal(str(l.end_balance)) for l in may_ledgers)
        print(f"May Total: {may_total}")
        
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

        june_ledgers = EpochLedger.query.filter(
            EpochLedger.fund_name.ilike('Axiom'),
            EpochLedger.epoch_end == june_end
        ).all()
        print(f"June Valuations count: {len(june_ledgers)}")
        if len(june_ledgers) > 0:
            june_total = sum(Decimal(str(l.end_balance)) for l in june_ledgers)
            print(f"June Valuations Total: {june_total}")

        all_investments_axiom = Investment.query.filter(Investment.fund_id == axiom.id).count()
        print(f"Total investments for Axiom: {all_investments_axiom}")
        expected_total = (may_total + june_principal) * Decimal("0.9975")
        print(f"Expected valuation at -0.25%: {expected_total}")
