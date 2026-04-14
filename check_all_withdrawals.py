import sys
sys.path.insert(0, '.')

from main import app, db
from app.Investments.model import Withdrawal
from sqlalchemy import func

with app.app_context():
    # Check all withdrawals
    all_wds = db.session.query(Withdrawal).all()
    
    print(f"Total withdrawals in DB: {len(all_wds)}\n")
    
    # Group by month
    from datetime import datetime
    monthly = {}
    for w in all_wds:
        month_key = w.date_withdrawn.strftime('%Y-%m') if w.date_withdrawn else 'No Date'
        if month_key not in monthly:
            monthly[month_key] = []
        monthly[month_key].append(w)
    
    for month in sorted(monthly.keys()):
        print(f"\n{month}:")
        for w in sorted(monthly[month], key=lambda x: (x.internal_client_code, x.amount)):
            print(f'  {w.internal_client_code:15} {w.fund_name:10} ${w.amount:>10,.2f}  {w.status}')
