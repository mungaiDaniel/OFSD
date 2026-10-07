#!/usr/bin/env python
import sys
sys.path.insert(0, '/c/Users/Dantez/Downloads/ofds/backend')

from app.main import app, db
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from datetime import datetime, timezone
from sqlalchemy import func

with app.app_context():
    print("=== Database Inventory ===\n")
    
    # Count total investments
    total_investments = db.session.query(func.count(Investment.id)).scalar()
    print(f"Total investments in DB: {total_investments}")
    
    # Get Aditum fund
    aditum = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == 'aditum').first()
    if not aditum:
        print("Aditum fund not found!")
        sys.exit(1)
    
    print(f"Aditum fund_id: {aditum.id}, is_active: {aditum.is_active}")
    
    # Count Aditum investments by fund_id
    aditum_by_id = db.session.query(func.count(Investment.id)).filter(
        Investment.fund_id == aditum.id
    ).scalar()
    print(f"\nAditum investments (by fund_id): {aditum_by_id}")
    
    # Count Aditum investments by name (legacy)
    aditum_by_name = db.session.query(func.count(Investment.id)).filter(
        func.lower(Investment.fund_name) == 'aditum'
    ).scalar()
    print(f"Aditum investments (by fund_name): {aditum_by_name}")
    
    # Count investments with fund_id = NULL
    null_fund_id = db.session.query(func.count(Investment.id)).filter(
        Investment.fund_id == None
    ).scalar()
    print(f"Investments with fund_id=NULL: {null_fund_id}")
    
    # Get batches for Aditum
    batches = db.session.query(Batch).join(
        Investment, Investment.batch_id == Batch.id
    ).filter(Investment.fund_id == aditum.id).distinct().all()
    
    print(f"\nBatches for Aditum (by fund_id):")
    for batch in batches:
        count = db.session.query(func.count(Investment.id)).filter(
            Investment.batch_id == batch.id,
            Investment.fund_id == aditum.id
        ).scalar()
        print(f"  {batch.batch_name} (id={batch.id}): {count} investors, deployed={batch.date_deployed}, is_active={batch.is_active}")
    
    # Count investments with date_deposited <= June 30, 2026
    june_cutoff = datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    aditum_by_june = db.session.query(func.count(Investment.id)).filter(
        Investment.fund_id == aditum.id,
        Investment.date_deposited <= june_cutoff
    ).scalar()
    print(f"\nAditum investments deposited by June 30, 2026: {aditum_by_june}")
    
    # Show specific investors
    print(f"\nSample Aditum investors:")
    aditum_investors = db.session.query(Investment).filter(
        Investment.fund_id == aditum.id,
        Investment.date_deposited <= june_cutoff
    ).limit(5).all()
    
    for inv in aditum_investors:
        print(f"  {inv.internal_client_code}: ${inv.amount_deposited} deposited {inv.date_deposited}, batch_id={inv.batch_id}")
