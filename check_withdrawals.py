"""
Check for withdrawals that might zero out weighted capital
"""
import sys
sys.path.insert(0, '.')

from app.database.database import db
from main import create_app
from config import DevelopmentConfig as Config
from app.Investments.model import Withdrawal

app = create_app(Config)

with app.app_context():
    print("=" * 80)
    print("CHECKING FOR WITHDRAWALS")
    print("=" * 80)
    
    # Check for any withdrawals
    all_withdrawals = db.session.query(Withdrawal).all()
    
    print(f"\nTotal withdrawals in database: {len(all_withdrawals)}")
    
    if len(all_withdrawals) > 0:
        for w in all_withdrawals:
            print(f"\n  Withdrawal:")
            print(f"    Code: {w.internal_client_code}")
            print(f"    Amount: ${w.amount}")
            print(f"    Fund ID: {w.fund_id}")
            print(f"    Status: {w.status}")
            print(f"    Date Withdrawn: {w.date_withdrawn}")
    else:
        print("✓ No withdrawals found - weighted capital should NOT be affected")
    
    # Check for Axiom-specific withdrawals
    axiom_withdrawals = db.session.query(Withdrawal).filter(
        (Withdrawal.fund_id == 1) & (Withdrawal.status == "Approved")
    ).all()
    
    print(f"\nApproved withdrawals for Axiom (fund_id=1): {len(axiom_withdrawals)}")
    if len(axiom_withdrawals) == 0:
        print("✓ No withdrawals will reduce weighted capital")
