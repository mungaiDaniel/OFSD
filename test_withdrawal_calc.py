#!/usr/bin/env python
"""
Test the backend investment calculation directly
"""
import sys
sys.path.insert(0, 'c:\\Users\\Dantez\\Downloads\\ofds\\backend')

from config import DevelopmentConfig as Config
from app.database.database import db
from flask import Flask
from app.Investments.model import Investment, Withdrawal, FINAL_WITHDRAWAL_STATUSES, EpochLedger
from app.Batch.model import Batch
from sqlalchemy import func
from decimal import Decimal
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import timedelta

# Setup app
app = Flask(__name__)
app.config.from_object(Config)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=1)
JWTManager(app)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})
db.init_app(app)
app.app_context().push()
db.create_all()

with app.app_context():
    session = db.session
    
    print("=" * 80)
    print("TESTING BACKEND WITHDRAWAL CALCULATION")
    print("=" * 80)
    
    # Get Batch 1
    batch = session.query(Batch).filter(Batch.id == 1).first()
    if not batch:
        print("Batch 1 not found")
        sys.exit(1)
    
    print(f"\nBatch 1: {batch.batch_name}")
    print(f"Date deployed: {batch.date_deployed}")
    print(f"Status: {batch.status}")
    
    # Get all investments in Batch 1
    investments = session.query(Investment).filter(Investment.batch_id == 1).all()
    print(f"\nTotal investments in Batch 1: {len(investments)}")
    
    for i, inv in enumerate(investments[:3]):  # Show first 3
        print(f"\n  [{i+1}] {inv.investor_name} ({inv.internal_client_code})")
        print(f"      Fund: {inv.fund.fund_name if inv.fund else inv.fund_name}")
        print(f"      Amount deposited: ${inv.amount_deposited}")
        
        # Get the fund_name for withdrawal lookup
        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        
        # Query withdrawals for this investor + fund with FINAL status
        total_approved_wds = session.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
            Withdrawal.internal_client_code == inv.internal_client_code,
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
            func.lower(Withdrawal.fund_name) == func.lower(fund_name)
        ).scalar() or Decimal("0")
        
        print(f"      ✓ Withdrawal query result (FINAL status): ${float(total_approved_wds)}")
        
        # Show individual withdrawal records
        wd_records = session.query(Withdrawal).filter(
            Withdrawal.internal_client_code == inv.internal_client_code,
            func.lower(Withdrawal.fund_name) == func.lower(fund_name)
        ).all()
        
        if wd_records:
            print(f"      Found {len(wd_records)} withdrawal records:")
            for wd in wd_records:
                print(f"        - {wd.status}: ${wd.amount}")
        else:
            print(f"      No withdrawal records found")
    
    print("\n" + "=" * 80)
