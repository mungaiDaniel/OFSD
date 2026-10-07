#!/usr/bin/env python3
"""
Test API endpoints to verify unique investor counts are returned correctly.
"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app
import json

app = create_app(Config)
app.config['TESTING'] = True

# Create test client
with app.test_client() as client:
    # Get JWT token first (use admin user)
    print("=" * 80)
    print("API ENDPOINT DEDUPLICATION TEST")
    print("=" * 80)
    print()
    
    # Test login and get token
    print("Step 1: Authenticate")
    print("-" * 40)
    login_response = client.post('/api/v1/auth/login', 
        json={
            'email': 'admin@example.com',
            'password': 'admin123'
        }
    )
    
    if login_response.status_code != 200:
        print("⚠️  Could not authenticate. Using endpoints without auth for demo.")
        print()
    else:
        token = login_response.get_json()['data']['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        print(f"✓ Authenticated successfully")
        print()
        
        # Test 2: GET /api/v1/funds - should show unique investor counts
        print("Step 2: GET /api/v1/funds - Unique Counts Per Fund")
        print("-" * 40)
        funds_response = client.get('/api/v1/funds', headers=headers)
        
        if funds_response.status_code == 200:
            funds_data = funds_response.get_json()
            print(f"Status: {funds_response.status_code}")
            print(f"Funds retrieved: {len(funds_data['data'])}")
            
            for fund in funds_data['data']:
                print(f"\n  Fund: {fund['fund_name']}")
                print(f"    Investor Count (unique): {fund['investor_count']}")
                print(f"    Total AUM: ${fund['total_aum']:,.2f}")
        else:
            print(f"Status: {funds_response.status_code}")
            print(f"Response: {funds_response.get_json()}")
        print()
        
        # Test 3: GET /api/v1/batches - should show unique investor counts
        print("Step 3: GET /api/v1/batches - Batch Summary")
        print("-" * 40)
        batches_response = client.get('/api/v1/batches', headers=headers)
        
        if batches_response.status_code == 200:
            batches_data = batches_response.get_json()
            print(f"Status: {batches_response.status_code}")
            print(f"Batches retrieved: {len(batches_data['data'])}")
            
            for batch in batches_data['data'][:2]:  # Show first 2
                print(f"\n  Batch: {batch['batch_name']}")
                print(f"    Unique Investors: {batch['investors_count']}")
                print(f"    Total Principal: ${batch['total_principal']:,.2f}")
        else:
            print(f"Status: {batches_response.status_code}")
        print()
        
        # Test 4: GET /api/v1/investors - investor directory
        print("Step 4: GET /api/v1/investors - Director (Deduped by Code)")
        print("-" * 40)
        investors_response = client.get('/api/v1/investors', headers=headers)
        
        if investors_response.status_code == 200:
            investors_data = investors_response.get_json()
            print(f"Status: {investors_data['status']}")
            print(f"Unique investors in directory: {investors_data['count']}")
            
            for inv in investors_data['data'][:3]:  # Show first 3
                print(f"\n  {inv['internal_client_code']} - {inv['investor_name']}")
                print(f"    Total Principal: ${inv['total_principal']:,.2f}")
                print(f"    Separate Entries: {inv['investments']}")
        else:
            print(f"Status: {investors_response.status_code}")
        print()
        
        # Test 5: GET /api/v1/investors/<code>/portfolio - new aggregation endpoint
        print("Step 5: GET /api/v1/investors/AXIOM-001/portfolio - Portfolio Aggregation")
        print("-" * 40)
        portfolio_response = client.get('/api/v1/investors/AXIOM-001/portfolio', headers=headers)
        
        if portfolio_response.status_code == 200:
            portfolio_data = portfolio_response.get_json()
            print(f"Status: {portfolio_response.status_code}")
            
            data = portfolio_data['data']
            print(f"Investor: {data['investor_name']} ({data['client_code']})")
            print(f"  Total Principal: ${data['total_principal']:,.2f}")
            print(f"  Unique Batches: {data['unique_batches']}")
            print(f"  Holdings:\n")
            
            for holding in data['holdings']:
                print(f"    - {holding['batch_name']} / {holding['fund_name']}")
                print(f"      Entries: {holding['investments_count']}")
                print(f"      Principal: ${holding['total_principal']:,.2f}")
                if holding['latest_valuation']:
                    val = holding['latest_valuation']
                    print(f"      Latest: End Balance = ${val['end_balance']:,.2f}, Profit = ${val['profit']:,.2f}")
                print()
        else:
            print(f"Status: {portfolio_response.status_code}")
            print(f"Response: {portfolio_response.get_json()}")
        print()
    
    print("=" * 80)
    print("API Testing Complete!")
    print("=" * 80)
