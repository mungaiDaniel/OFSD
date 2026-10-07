#!/usr/bin/env python
"""
Check if EpochLedger has withdrawal data (to understand uncaptured_wds calculation)
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
JWTManager(app)
CORS(app, supports_credentials=True)
db.init_app(app)
app.app_context().push()

with app.app_context():
    session = db.session
    
    print("=" * 80)
    print("EPOCH LEDGER WITHDRAWAL ANALYSIS")
    print("=" * 80)
    
    # Get Batch 1
    batch = session.query(Batch).filter(Batch.id == 1).first()
    if not batch:
        print("Batch 1 not found")
        sys.exit(1)
    
    # Get a sample investment from Batch 1
    investment = session.query(Investment).filter(Investment.batch_id == 1).first()
    if not investment:
        print("No investments in Batch 1")
        sys.exit(1)
    
    print(f"\nAnalyzing investment: {investment.investor_name} ({investment.internal_client_code})")
    print(f"Fund: {investment.fund.fund_name if investment.fund else investment.fund_name}")
    
    fund_name = investment.fund.fund_name if investment.fund else investment.fund_name
    
    # Check Withdrawal table
    total_approved_wds = session.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
        Withdrawal.internal_client_code == investment.internal_client_code,
        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
        func.lower(Withdrawal.fund_name) == func.lower(fund_name)
    ).scalar() or Decimal("0")
    
    print(f"\n1. Total Approved Withdrawals (Withdrawal table with FINAL status):")
    print(f"   ${float(total_approved_wds)}")
    
    # Check EpochLedger
    total_captured_wds = session.query(func.coalesce(func.sum(EpochLedger.withdrawals), 0)).filter(
        EpochLedger.internal_client_code == investment.internal_client_code,
        func.lower(EpochLedger.fund_name) == func.lower(fund_name)
    ).scalar() or Decimal("0")
    
    print(f"\n2. Total Captured Withdrawals (EpochLedger table):")
    print(f"   ${float(total_captured_wds)}")
    
    # Calculate uncaptured
    uncaptured_wds = max(Decimal("0"), Decimal(str(total_approved_wds)) - Decimal(str(total_captured_wds)))
    print(f"\n3. Uncaptured Withdrawals (for proportional allocation):")
    print(f"   ${float(uncaptured_wds)}")
    
    # Show individual EpochLedger records
    epochs = session.query(EpochLedger).filter(
        EpochLedger.internal_client_code == investment.internal_client_code,
        func.lower(EpochLedger.fund_name) == func.lower(fund_name)
    ).order_by(EpochLedger.epoch_end.desc()).all()
    
    print(f"\n4. EpochLedger records for this investor/fund: {len(epochs)}")
    if epochs:
        for epoch in epochs[:5]:
            print(f"   - Epoch end {epoch.epoch_end}: withdrawals = ${epoch.withdrawals}")
    else:
        print(f"   *** NO EPOCH LEDGER RECORDS FOUND ***")
    
    print("\n" + "=" * 80)
    print("INTERPRETATION:")
    if float(uncaptured_wds) == 0:
        print("  ⚠️  uncaptured_wds = 0 → withdrawal_share will be 0")
        print("     This means ALL withdrawals are already captured in EpochLedger.")
        print("     The backend will return withdrawals = 0 for this investment.")
    else:
        print(f"  ✓ uncaptured_wds = ${float(uncaptured_wds)}")
        print("   Withdrawals will be prorated based on investment's share of holdings.")
    print("=" * 80)
