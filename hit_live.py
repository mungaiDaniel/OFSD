import urllib.request
import json
from main import app
from flask_jwt_extended import create_access_token

with app.app_context():
    token = create_access_token(identity="1")

req = urllib.request.Request("http://127.0.0.1:5000/api/stats/overview", headers={"Authorization": f"Bearer {token}"})
try:
    with urllib.request.urlopen(req) as response:
        print(response.getcode())
        print(response.read().decode())
except Exception as e:
    print("Error:", e)
