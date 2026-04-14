import os
import sys

# Add backend dir to python path
sys.path.append(r'C:\Users\Dantez\Downloads\ofds\backend')

from app.database.database import db
from app.Investments.models import Withdrawal
from main import app

with app.app_context():
    withdrawals = Withdrawal.query.all()
    print("WITHDRAWALS FOUND:", len(withdrawals))
    for w in withdrawals:
        print(f"ID: {w.id}, Client: {w.internal_client_code}, Amount: {w.amount}, Status: {w.status}")
