from app.main import app, db
from app.Valuation.model import ValuationRun
from app.logic.valuation_service import PortfolioValuationService
from datetime import datetime, timezone

with app.app_context():
    try:
        print("Calling preview_epoch_for_fund_name for Aditum June 2026...")
        preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name='Aditum',
            start_date=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
            performance_rate=0.0348,  # 3.48%
            session=db.session,
        )
        print('\n=== PREVIEW RESULT ===')
        print(f'Total investors processed: {preview.get("investors_processed")}')
        print(f'Performance Applied: ${preview.get("performance_applied"):.2f}')
        print(f'Total Active Capital: ${preview.get("total_active_capital"):.2f}')
        print(f'Total Profit: ${preview.get("total_profit"):.2f}')
        print(f'Expected Closing AUM: ${preview.get("expected_closing_aum"):.2f}')
        print(f'Reconciliation Total: ${preview.get("reconciliation_total"):.2f}')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
