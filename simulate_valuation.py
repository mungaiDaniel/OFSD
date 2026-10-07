import os
import sys

# Add the project root to sys.path so we can import 'app'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from datetime import datetime, timezone
from decimal import Decimal

from flask import Flask
from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Performance.model import Performance
import config

app = Flask(__name__)
# Assuming config is in the same directory and has DevelopmentConfig
app.config.from_object(config.DevelopmentConfig)
db.init_app(app)

with app.app_context():
    axiom = CoreFund.query.filter(CoreFund.fund_name.ilike('Axiom')).first()
    if axiom:
        start_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
        end_date = datetime(2026, 6, 30, tzinfo=timezone.utc)
        print(f"Testing valuation for Axiom (ID: {axiom.id}) run for {start_date} to {end_date}")
        
        try:
            inputs = PortfolioValuationService._build_investor_inputs(
                fund_id=axiom.id,
                fund_name=axiom.fund_name,
                start_date=start_date,
                end_date=end_date,
                session=db.session
            )
            print("Investor inputs built successfully:")
            for k, v in inputs.items():
                print(f" - {k}: active_capital={v.active_capital}, deposits={v.deposits_during_period}, principal={v.principal_before_start}")
        except Exception as e:
            print(f"Error building investor inputs: {e}")
            import traceback
            traceback.print_exc()

        try:
            res = PortfolioValuationService.create_epoch_ledger_for_fund(
                fund_id=axiom.id,
                start_date=start_date,
                end_date=end_date,
                performance_rate=-0.0025,
                head_office_total="4967575.34",
                session=db.session
            )
            print("Epoch ledger run successful:", res)
        except Exception as e:
            print(f"Error in create_epoch_ledger_for_fund: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Axiom fund not found.")
