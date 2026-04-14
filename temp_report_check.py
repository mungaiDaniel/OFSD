from main import create_app
from config import DevelopmentConfig
from flask_jwt_extended import create_access_token

app = create_app(DevelopmentConfig)
ctx = app.app_context()
ctx.push()
try:
    token = create_access_token(identity='admin@example.com', additional_claims={'admin': 1})
    client = app.test_client()
    resp = client.get('/api/v1/reports', headers={'Authorization': 'Bearer ' + token})
    print('STATUS', resp.status_code)
    print(resp.get_data(as_text=True))
finally:
    ctx.pop()
