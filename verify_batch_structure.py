#!/usr/bin/env python3
"""
Verify Batch IDs and deployment date mapping per user requirements
Run from: backend directory
"""

import sys  
import os

# Add current directory to path so we can import app
sys.path.insert(0, os.path.dirname(__file__))

def verify_batch_structure():
    try:
        from app import create_app
        from app.database.database import db
        from app.Batch.model import Batch
        from app.Investments.model import Investment
        
        app = create_app()
        with app.app_context():
            session = db.session
            
            print("\n" + "=" * 100)
            print("BATCH STRUCTURE VERIFICATION")
            print("=" * 100)
            
            batches = session.query(Batch).all()
            
            print(f"\nTotal batches: {len(batches)}\n")
            
            for batch in batches:
                inv_count = session.query(Investment).filter(
                    Investment.batch_id == batch.id
                ).count()
                
                unique_investors = session.query(
                    Investment.internal_client_code
                ).filter(
                    Investment.batch_id == batch.id
                ).distinct().count()
                
                print(f"Batch ID: {batch.id}")
                print(f"  Name: {batch.batch_name}")
                print(f"  Date Deployed: {batch.date_deployed}")
                print(f"  Total Investments: {inv_count}")
                print(f"  Unique Investors: {unique_investors}")
                print(f"  Status: {'Active' if batch.is_active else 'Inactive'}")
                print()
            
            # Per user requirements, verify these batch/date mappings:
            print("\nEXPECTED BATCH DATES (per user requirements):")
            print("  Batch 1 (Q1-2026): 07 Apr 2026")
            print("  Batch 2 (Q1-2028): 10 Sept 2026")
            print("  Batch 3 (Portfolio 3): 01 Oct 2026")
            
            from datetime import datetime
            print("\nACTUAL BATCH DATES:")
            for batch in sorted(batches, key=lambda b: b.date_deployed or datetime.min):
                if batch.date_deployed:
                    print(f"  {batch.batch_name}: {batch.date_deployed.strftime('%d %b %Y')}")
            
            print("\n" + "=" * 100)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_batch_structure()
