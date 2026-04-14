from app.database.database import db
from app.Investments.model import EpochLedger, Investment, Withdrawal
from app import create_app
app = create_app()
with app.app_context():
    print('--- Investments ---')
    for inv in Investment.query.filter_by(internal_client_code='AXIOM-001').all():
        print(f'Batch: {inv.batch_id}, Fund: {inv.fund_id}, Amount: {inv.amount_deposited}')
    print('--- Withdrawals ---')
    for w in Withdrawal.query.filter_by(internal_client_code='AXIOM-001').all():
        print(f'Amount: {w.amount}, Status: {w.status}, Fund: {w.fund_id}')
    print('--- EpochLedger ---')
    for led in EpochLedger.query.filter_by(internal_client_code='AXIOM-001').all():
        print(f'Deposits: {led.deposits}, Withdrawals: {led.withdrawals}, Profit: {led.profit}, End: {led.end_balance}')
