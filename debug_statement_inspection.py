from main import create_app
import config
from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Investments.route import get_investor_statements

app = create_app(config.DevelopmentConfig)
ctx = app.app_context(); ctx.push()

# Find a candidate investor with Axiom fund and June/July 2026 entries
candidate = None
for inv in db.session.query(Investment).filter(Investment.fund_name.ilike('%axiom%')).limit(200).all():
    ledgers = db.session.query(EpochLedger).filter(EpochLedger.internal_client_code == inv.internal_client_code).all()
    if any(l.epoch_end and l.epoch_end.year == 2026 and l.epoch_end.month in (6, 7) for l in ledgers):
        candidate = inv.internal_client_code
        break

print('candidate', candidate)
if not candidate:
    raise SystemExit('No candidate found')

resp = get_investor_statements(candidate)
print('status', resp.status_code)
print(resp.get_json())

print('\nInvestments:')
for inv in db.session.query(Investment).filter(Investment.internal_client_code == candidate).order_by(Investment.date_deposited).all():
    print(inv.internal_client_code, inv.batch_id, float(inv.amount_deposited), inv.date_deposited, inv.fund_name)

print('\nWithdrawals:')
for wd in db.session.query(Withdrawal).filter(Withdrawal.internal_client_code == candidate).order_by(Withdrawal.date_withdrawn).all():
    print(float(wd.amount), wd.date_withdrawn, wd.status, wd.fund_name)

print('\nLedger:')
for l in db.session.query(EpochLedger).filter(EpochLedger.internal_client_code == candidate).order_by(EpochLedger.epoch_end).all():
    print(l.epoch_end, float(l.start_balance), float(l.deposits), float(l.withdrawals), float(l.profit), float(l.end_balance), float(l.performance_rate or 0))

ctx.pop()
