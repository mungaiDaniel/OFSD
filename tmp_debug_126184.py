import os
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment, EpochLedger
from app.Batch.model import Batch
from app.Valuation.model import Statement, ValuationRun
from app.Batch.controllers import BatchController

os.environ.setdefault('FLASK_ENV', 'development')
app = create_app(Config)

with app.app_context():
    code = '126184.0'
    print('=== INVESTMENTS ===')
    invs = db.session.query(Investment).filter(Investment.internal_client_code == code).order_by(Investment.batch_id, Investment.date_deposited).all()
    print('count', len(invs))
    for inv in invs:
        print('INV', inv.id, inv.batch_id, inv.internal_client_code, inv.fund_name, float(inv.amount_deposited), float(inv.net_principal), inv.date_deposited, inv.fund_id)
    print('=== BATCHES ===')
    batch_ids = sorted({inv.batch_id for inv in invs if inv.batch_id is not None})
    for bid in batch_ids:
        b = db.session.query(Batch).filter(Batch.id == bid).first()
        print('BATCH', bid, b.batch_name, b.date_deployed, getattr(b, 'is_active', None))
    print('=== STATEMENTS ===')
    stmts = db.session.query(Statement).join(ValuationRun, Statement.valuation_run_id == ValuationRun.id).filter(Statement.batch_id.in_(batch_ids), Statement.investor_id.in_([inv.id for inv in invs]), ValuationRun.status.ilike('committed')).order_by(Statement.batch_id, ValuationRun.epoch_end).all()
    for st in stmts:
        vr = db.session.query(ValuationRun).filter(ValuationRun.id == st.valuation_run_id).first()
        print('ST', st.id, st.investor_id, st.batch_id, float(st.opening_balance), float(st.closing_balance), float(st.performance_gain), vr.epoch_end, float(vr.performance_rate))
    print('=== EPOCH LEDGER ===')
    leds = db.session.query(EpochLedger).filter(EpochLedger.internal_client_code == code).order_by(EpochLedger.epoch_end).all()
    for l in leds:
        print('EL', l.id, l.fund_name, l.epoch_start, l.epoch_end, float(l.start_balance), float(l.deposits), float(l.withdrawals), float(l.profit), float(l.end_balance))
    print('=== BATCH VALUES PER INVESTMENT ===')
    for inv in invs:
        batch = db.session.query(Batch).filter(Batch.id == inv.batch_id).first()
        val = BatchController._calculate_batch_investment_values(inv, batch, db.session)
        print('VAL', inv.id, inv.batch_id, val)
