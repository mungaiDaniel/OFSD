#!/usr/bin/env python3
"""Test the get_batch_history endpoint directly"""
import sys
from main import create_app
from config import DevelopmentConfig as Config
from flask.testing import FlaskClient

app = create_app(Config)
client = app.test_client()

# Test the endpoint
print("\nTesting GET /api/v1/batches/1/history")
print("=" * 60)

# Since it requires JWT, we'll use the test client which bypasses auth
with app.test_request_context():
    # Directly call the endpoint function
    from app.Batch.route import get_batch_history
    from flask_jwt_extended import create_access_token
    
    # Create a valid token for testing
    with app.app_context():
        access_token = create_access_token(identity="test-user")
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = client.get('/api/v1/batches/1/history', headers=headers)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response:")
        import json
        data = response.get_json()
        print(json.dumps(data, indent=2))

print("\n" + "=" * 60)
