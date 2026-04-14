import urllib.request
import json
from main import app
from flask_jwt_extended import create_access_token
from app.database.database import db
from app.Investments.model import Investment

with app.app_context():
    invs = db.session.query(Investment).filter(Investment.internal_client_code == 'AXIOM-002').all()
    for inv in invs:
        print(f"Batch: {inv.batch_id}, Fund: {inv.fund_name}, Amt: {inv.amount_deposited}, Date: {inv.date_deposited}")
