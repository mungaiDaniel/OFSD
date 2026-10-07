import main
from app.database.database import db
from sqlalchemy import text

with main.app.app_context():
    result = db.session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='investments' AND column_name='rounding_adjustment'"))
    print(result.fetchall())
