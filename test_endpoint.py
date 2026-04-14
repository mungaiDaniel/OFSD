from main import app
from flask_jwt_extended import create_access_token

with app.app_context():
    token = create_access_token(identity="1")
    with app.test_client() as client:
        res = client.get("/api/stats/overview", headers={"Authorization": f"Bearer {token}"})
        print("Status:", res.status_code)
        try:
            print("Response:", res.json)
        except:
            print("Response text:", res.data)
