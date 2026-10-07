from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import Investment
from sqlalchemy import func

app = create_app(Config)

with app.app_context():
    # Get distinct client codes
    codes = db.session.query(func.distinct(Investment.internal_client_code)).limit(20).all()
    print("Available client codes:")
    for code in codes:
        print(f"  {code[0]}")
    print(f"Total: {len(codes)}")
