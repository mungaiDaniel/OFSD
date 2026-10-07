from app.database.database import db
from app.Investments.model import Investment, EpochLedger
from app.Performance.pro_rata_distribution import ProRataDistribution
from flask import Flask

app = Flask(__name__)
app.config.from_object('config.Config')
db.init_app(app)

with app.app_context():
    # Let's look at John Smith in Axiom
    client_code = 'AXIOM-001'
    invs = Investment.query.filter_by(internal_client_code=client_code).all()
    print("Investments for John Smith:")
    for inv in invs:
        print(f"ID: {inv.id}, Batch: {inv.batch_id}, Amount: {inv.amount_deposited}, Date: {inv.date_deposited}")
        pro_ratas = ProRataDistribution.query.filter_by(investment_id=inv.id).order_by(ProRataDistribution.calculation_date).all()
        profit = sum(pr.profit_allocated for pr in pro_ratas)
        print(f"  Total Profit Allocated (ProRata): {profit}")
    
    epochs = EpochLedger.query.filter_by(internal_client_code=client_code).order_by(EpochLedger.epoch_end).all()
    print("\nEpochLedger for John Smith:")
    for ep in epochs:
        print(f"End: {ep.epoch_end}, Start Bal: {ep.start_balance}, Dep: {ep.deposits}, Profit: {ep.profit}, End Bal: {ep.end_balance}")

