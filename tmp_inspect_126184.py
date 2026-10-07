from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment, EpochLedger
from app.Valuation.model import Statement, ValuationRun
import os

os.environ.setdefault('FLASK_ENV', 'development')
app = create_app(Config)

with app.app_context():
    code = '126184.0'
    invs = db.session.query(Investment).filter(Investment.internal_client_code == code).order_by(Investment.batch_id, Investment.date_deposited).all()
    print('INVESTMENTS', len(invs))
    for inv in invs:
        print('INV', inv.id, inv.internal_client_code, inv.batch_id, inv.batch.batch_name if inv.batch else None, inv.fund_name, float(inv.net_principal), inv.amount_deposited, inv.date_deposited)

    print('\nSTATEMENTS', flush=True)
    sts = db.session.query(Statement, ValuationRun).join(ValuationRun, Statement.valuation_run_id == ValuationRun.id).filter(Statement.investor_id.in_([inv.id for inv in invs])).order_by(Statement.batch_id, ValuationRun.epoch_end).all()
    print('STATEMENTS', len(sts))
    for st, vr in sts:
        print('ST', st.id, st.investor_id, st.batch_id, st.fund_id, float(st.opening_balance), float(st.closing_balance), float(st.performance_gain), vr.epoch_end, vr.status)

    leds = db.session.query(EpochLedger).filter(EpochLedger.internal_client_code == code).order_by(EpochLedger.epoch_end).all()
    print('\nLEDGERS', len(leds))
    for l in leds:
        print('EL', l.id, l.fund_name, l.epoch_start, l.epoch_end, float(l.start_balance), float(l.deposits), float(l.withdrawals), float(l.profit), float(l.end_balance))
