from app.database.database import db
from main import app
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE investments DROP CONSTRAINT _customer_batch_uc;'))
        db.session.commit()
        print("Successfully dropped constraint _customer_batch_uc")
    except Exception as e:
        db.session.rollback()
        print(f"Error dropping constraint: {e}")
