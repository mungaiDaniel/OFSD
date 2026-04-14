from flask import Flask
from config import DevelopmentConfig as Config
from app.database.database import db
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE valuation_runs ADD COLUMN is_committed BOOLEAN NOT NULL DEFAULT true;'))
        db.session.commit()
        print('Pushed alteration')
    except Exception as e:
        print('Error:', e)
        db.session.rollback()
