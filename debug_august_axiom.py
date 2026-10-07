from flask import Flask
from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService
from app.Batch.core_fund import CoreFund
# Import all relevant models to ensure SQLAlchemy mappers are initialized
from app.Valuation.model import ValuationRun, Statement
from app.Performance.model import Performance
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal

from datetime import datetime, timezone
import config
from decimal import Decimal

app = Flask(__name__)
app.config.from_object(config.DevelopmentConfig)
db.init_app(app)

with app.app_context():
    fund_name = "Axiom"
    start_date = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 8, 31, tzinfo=timezone.utc)
    performance_rate = 0.0253
    
    print(f"Checking data for {fund_name} in August 2026...")
    try:
        axiom = CoreFund.query.filter(CoreFund.fund_name.ilike(fund_name)).first()
        if not axiom:
            print("Axiom fund not found")
        else:
            print(f"Fund Active: {axiom.is_active}")
            
        # Check previous ledger (July? or most recent before August)
        prev = EpochLedger.query.filter(EpochLedger.fund_name.ilike(fund_name)).order_by(EpochLedger.epoch_end.desc()).first()
        if prev:
            print(f"Last Ledger End: {prev.epoch_end}, Total Balance: {db.session.query(db.func.sum(EpochLedger.end_balance)).filter(EpochLedger.fund_name.ilike(fund_name), EpochLedger.epoch_end == prev.epoch_end).scalar()}")
        
        # Check August investments
        aug_invs = Investment.query.filter(Investment.fund_id == axiom.id, Investment.date_deposited >= start_date, Investment.date_deposited <= end_date).all()
        print(f"August New Investments: {len(aug_invs)}, Sum: {sum(i.amount_deposited for i in aug_invs)}")
        
        # Dry Run
        preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name=fund_name,
            start_date=start_date,
            end_date=end_date,
            performance_rate=performance_rate,
            session=db.session
        )
        print("Dry run successful!")
        
    except Exception as e:
        print(f"Error: {e}")
