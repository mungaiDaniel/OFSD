import requests

# Test if we can reach the API
try:
    response = requests.get("http://localhost:5000/api/v1/withdrawals", timeout=5)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nNumber of withdrawals: {len(data) if isinstance(data, list) else 'N/A'}")
        if isinstance(data, list) and len(data) > 0:
            print(f"\nFirst withdrawal:")
            import json
            print(json.dumps(data[0], indent=2))
except Exception as e:
    print(f"Error: {e}")
