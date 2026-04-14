#!/usr/bin/env python
"""Quick test to see if investors are being returned from the database"""

import sys
sys.path.insert(0, '/home/app')

from app.database.database import db
from app.Investments.model import Investment
from main import create_app

app = create_app()

with app.app_context():
    # Test 1: Count all investments
    total_investments = db.session.query(Investment).count()
    print(f"✓ Total investments in database: {total_investments}")
    
    # Test 2: Get distinct client codes
    client_codes = db.session.query(Investment.internal_client_code).distinct().all()
    print(f"✓ Distinct client codes: {[c[0] for c in client_codes]}")
    
    # Test 3: Try to get ATIUM-008 specifically
    atium_008_invs = db.session.query(Investment).filter(
        Investment.internal_client_code == "ATIUM-008"
    ).all()
    print(f"✓ Investments for ATIUM-008: {len(atium_008_invs)}")
    
    if atium_008_invs:
        inv = atium_008_invs[0]
        print(f"  - First investment: {inv.investor_name} - {inv.amount_deposited}")
        print(f"  - Fund name: {inv.fund_name}")
        print(f"  - Fund ID: {inv.fund_id}")
        print(f"  - Batch ID: {inv.batch_id}")
