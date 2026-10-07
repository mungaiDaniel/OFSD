#!/usr/bin/env python
"""Test script to check what the API returns for withdrawals"""
import requests
import json

try:
    url = 'http://localhost:5000/api/v1/batches/1'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        print("=" * 60)
        print("API Response for /api/batches/1")
        print("=" * 60)
        
        if 'investments' in data:
            print(f"\nTotal investments: {len(data['investments'])}")
            print("\nFirst 3 investments:")
            for inv in data['investments'][:3]:
                print(f"\n  Investor: {inv.get('investor_name', 'MISSING')}")
                print(f"    - investor_name: {inv.get('investor_name')}")
                print(f"    - internal_client_code: {inv.get('internal_client_code')}")
                print(f"    - fund_name: {inv.get('fund_name')}")
                print(f"    - amount_deposited: {inv.get('amount_deposited')}")
                print(f"    - withdrawals: {inv.get('withdrawals', 'KEY MISSING!')}")
                print(f"    - profit: {inv.get('profit')}")
        else:
            print('Key "investments" not in response')
            print('Top-level keys:', list(data.keys()) if isinstance(data, dict) else str(type(data)))
    else:
        print(f'HTTP Error: {response.status_code}')
        print(f'Response: {response.text[:500]}')
except Exception as e:
    print(f"Error: {e}")
    print("Make sure the backend is running on localhost:5000")
