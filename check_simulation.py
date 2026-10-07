from flask import Flask
from app.database.database import db
from app.Batch.controllers import BatchController
from app.Investments.model import Investment
from datetime import datetime, timezone

app = Flask(__name__)
# app.config.from_object('config.Config')
# mock config since import failed
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:username@localhost/offshow_dev'
db.init_app(app)

with app.app_context():
    session = db.session
    invs = session.query(Investment).filter_by(internal_client_code='AXIOM-001').all()
    for inv in invs:
        print(f"=== ID {inv.id} Batch {inv.batch_id} ===")
        # Get simulation
        balances = BatchController._simulate_client_fund_balances(inv, session)
        if balances and inv.id in balances:
            state = balances[inv.id]
            print(f"Full sim balance: {state['balance']}, profit: {state['profit']}")
