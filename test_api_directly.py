#!/usr/bin/env python3
"""Test the actual API endpoint that the UI calls"""
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)

# Simulate what the UI sends
test_payload = {
    "fund_name": "Atium",
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "performance_rate": 5,
    "head_office_total": 220500
}

print('=== SIMULATING UI DRY-RUN REQUEST ===\n')
print(f'Payload: {test_payload}')
print()

with app.test_client() as client:
    # Call the actual dry-run endpoint
    response = client.post(
        '/api/v1/valuation/dry-run',
        json=test_payload,
        headers={'Authorization': 'Bearer fake-token'}  # Skip auth for testing
    )
    
    print(f'Status: {response.status_code}')
    print(f'Response:')
    
    import json
    data = response.get_json()
    print(json.dumps(data, indent=2))
