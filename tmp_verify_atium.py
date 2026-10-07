import sys
sys.path.insert(0, '.')
from main import app
from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment
from sqlalchemy import func
from datetime import datetime, timezone

with app.app_context():
    # Find the Atium core fund
    core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == 'atium').first()
    if not core:
        print('ERROR: Atium fund not found')
        sys.exit(1)
    print(f'Fund: {core.fund_name} (id={core.id})')

    start_date = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end_date   = datetime(2026, 11, 30, tzinfo=timezone.utc)
    perf_rate  = 0.0410  # 4.10%
    head_office_total = 458170.29

    # Show all investments for Atium and their date_deposited
    all_invs = db.session.query(Investment).filter(Investment.fund_id == core.id).all()
    print(f'\nAll investments in Atium (total={len(all_invs)}):')
    for inv in sorted(all_invs, key=lambda x: x.date_deposited or datetime.min):
        eligible = (inv.date_deposited is not None and inv.date_deposited < start_date) or False
        dd = inv.date_deposited.date() if inv.date_deposited else 'N/A'
        print(f'  id={inv.id:3d}  code={inv.internal_client_code:12s}  batch_id={inv.batch_id}  deposited={dd}  amount={inv.amount_deposited}  eligible={eligible}')

    print()
    print('--- Running dry-run preview (date-gate applied) ---')
    preview = PortfolioValuationService.preview_epoch_for_fund_name(
        fund_name='Atium',
        start_date=start_date,
        end_date=end_date,
        performance_rate=perf_rate,
        session=db.session,
    )

    diff = round(abs(preview['reconciliation_total'] - head_office_total), 2)

    print()
    print('=== RESULTS ===')
    print(f'  total_rows_detected    : {preview.get("total_rows_detected", 0)}  (target: 4)')
    print(f'  total_active_capital   : {preview.get("total_active_capital", 0):,.2f}')
    print(f'  reconciliation_total   : {preview.get("reconciliation_total", 0):,.2f}  (target: 458,170.29)')
    print(f'  reconciliation_diff    : {diff:,.2f}  (target: <=0.01)')
    print(f'  is_reconciled          : {diff <= 0.01}')
    print()
    print('--- Investor Breakdown ---')
    for inv in preview.get('investor_breakdown', []):
        print(f'  {inv["internal_client_code"]:12s}  active_capital={inv["active_capital"]:>12,.2f}  profit={inv["profit"]:>10,.2f}')
