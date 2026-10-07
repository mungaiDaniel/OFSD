from app.database.database import db
from app import create_app
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE statements ADD COLUMN withdrawals NUMERIC(20,2) NOT NULL DEFAULT 0.00;'))
        db.session.commit()
        print("Successfully added withdrawals column to statements table.")
    except Exception as e:
        print(f"Error or column already exists: {e}")
        db.session.rollback()
