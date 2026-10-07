from flask import Flask
from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from datetime import datetime
from decimal import Decimal
import os

app = Flask(__name__)
# Absolute path to be safe
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///c:/Users/Dantez/Downloads/ofds/backend/instance/ofds.db'
db.init_app(app)

with app.app_context():
    # Trigger model discovery
    from sqlalchemy import inspect
    
    axiom = CoreFund.query.filter(CoreFund.fund_name.ilike('Axiom')).first()
    if not axiom:
        print("Axiom fund not found")
    else:
        print(f"Axiom Fund ID: {axiom.id}")
        
        # Check May Valuations
        # User says May Valuation was 2,056,025.40
        may_end = datetime(2026, 5, 31)
        may_ledgers = EpochLedger.query.filter(
            EpochLedger.fund_name.ilike('Axiom'),
            EpochLedger.epoch_end == may_end
        ).all()
        
        may_total = sum(Decimal(str(l.end_balance)) for l in may_ledgers)
        print(f"May Valuations Total: {may_total}")
        print(f"Count of May records: {len(may_ledgers)}")
        if len(may_ledgers) > 0:
            print(f"First May ledger end balance: {may_ledgers[0].end_balance}")
        
        # Check June Investments
        # User says June Principal 2,924,000.00
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
        
        # Check June Valuations
        june_ledgers = EpochLedger.query.filter(
            EpochLedger.fund_name.ilike('Axiom'),
            EpochLedger.epoch_end == june_end
        ).all()
        print(f"June Valuations count: {len(june_ledgers)}")
        if len(june_ledgers) > 0:
            june_total = sum(Decimal(str(l.end_balance)) for l in june_ledgers)
            print(f"June Valuations Total: {june_total}")

        # Check for any discrepancies in names or IDs
        all_investments_axiom = Investment.query.filter(Investment.fund_id == axiom.id).count()
        print(f"Total investments for Axiom: {all_investments_axiom}")
        
        # Check for specific investments mentioned
        # The user says -0.25% loss
        # Total should be (2,056,025.40 + 2,924,000.00) * 0.9975 = 4,967,575.3365 -> 4,967,575.34
