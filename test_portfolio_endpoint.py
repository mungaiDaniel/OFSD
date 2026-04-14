#!/usr/bin/env python
"""
Test the investor portfolio endpoint to verify atomic batch simulation works.
"""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.models.models import db, Investment, Batch
from flask_jwt_extended import create_access_token

app = create_app()

with app.app_context():
    # List all investors
    all_invs = db.session.query(Investment).distinct(
        Investment.internal_client_code
    ).all()
    
    if all_invs:
        investor_codes = sorted(set(inv.internal_client_code for inv in all_invs))
        print(f"Found {len(investor_codes)} investors:")
        for code in investor_codes[:5]:  # Show first 5
            count = db.session.query(Investment).filter(
                Investment.internal_client_code == code
            ).count()
            print(f"  - {code}: {count} investments")
        
        # Test portfolio endpoint with first investor
        test_code = investor_codes[0]
        print(f"\nTesting portfolio endpoint with {test_code}...")
        
        with app.test_client() as client:
            # Create JWT token
            access_token = create_access_token(identity='test-user')
            
            # Try to fetch portfolio
            response = client.get(
                f'/api/v1/investors/{test_code}/portfolio',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json
                print(f"✅ Portfolio retrieved successfully")
                print(f"   Client Code: {data['data']['client_code']}")
                print(f"   Investor Name: {data['data']['investor_name']}")
                print(f"   Total Principal: ${data['data']['total_principal']:,.2f}")
                print(f"   Current Balance: ${data['data']['current_balance']:,.2f}")
                print(f"   Total Profit: ${data['data']['total_profit']:,.2f}")
                print(f"   Unique Batches: {data['data']['unique_batches']}")
                print(f"   Holdings Count: {len(data['data']['holdings'])}")
                
                print(f"\n   Holdings Breakdown:")
                for h in data['data']['holdings']:
                    val = h.get('latest_valuation', {})
                    print(f"     - Batch {h['batch_id']} ({h['batch_name']}) / {h['fund_name']}")
                    print(f"       Principal: ${h['total_principal']:,.2f}")
                    print(f"       End Balance: ${val.get('end_balance', 0):,.2f}")
                    print(f"       Profit: ${val.get('profit', 0):,.2f}")
            else:
                print(f"❌ Error: {response.json}")
    else:
        print("No investors found in database")
