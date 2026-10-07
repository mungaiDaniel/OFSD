import sys
sys.path.insert(0, '.')

from main import app, db
from app.Investments.model import Withdrawal

with app.app_context():
    wds = db.session.query(Withdrawal).filter(
        Withdrawal.date_withdrawn >= '2026-05-01',
        Withdrawal.date_withdrawn <= '2026-05-31'
    ).all()
    
    print(f"Found {len(wds)} withdrawals in May 2026:\n")
    for w in wds:
        print(f'  Code: {w.internal_client_code:15} Fund: {w.fund_name:10} Amount: ${w.amount:>10,.2f}  Status: {w.status}')
