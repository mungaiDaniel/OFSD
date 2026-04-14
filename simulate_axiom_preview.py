from flask import Flask
from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService
from app.Batch.core_fund import CoreFund
# Import all relevant models to ensure SQLAlchemy mappers are initialized
from app.Valuation.model import ValuationRun, Statement
from app.Performance.model import Performance
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal

from datetime import datetime
import config
from decimal import Decimal

app = Flask(__name__)
app.config.from_object(config.DevelopmentConfig)
db.init_app(app)

with app.app_context():
    fund_name = "Axiom"
    # Use timezone-aware UTC for consistency with route logic
    from datetime import timezone
    start_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 6, 30, tzinfo=timezone.utc)
    performance_rate = -0.0025
    
    # Simulate preview_epoch_for_fund_name
    print(f"Simulating preview for {fund_name}...")
    try:
        preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name=fund_name,
            start_date=start_date,
            end_date=end_date,
            performance_rate=performance_rate,
            session=db.session
        )
        print(f"Gross Principal in preview: {preview['gross_principal']}")
        print(f"Excel Total in preview: {preview['excel_total']}")
        print(f"Total Profit in preview: {preview['total_profit']}")
        print(f"Investor rows: {preview['investor_rows']}")
        
        # Check breakdown
        print("\nBreakdown (first 5):")
        for i, b in enumerate(preview['investor_breakdown'][:5]):
            print(f"  {b['internal_client_code']}: start={b['principal_before_start']}, deposits={b['deposits_during_period']}, active={b['active_capital']}")
            
        # Check why it's missing 1.48M
        target_gross = 4980025.40
        missing = float(Decimal("4980025.40") - Decimal(str(preview['gross_principal'])))
        print(f"\nMissing from Gross Principal: {missing}")
        
    except Exception as e:
        print(f"Error during simulation: {e}")
        import traceback
        traceback.print_exc()
