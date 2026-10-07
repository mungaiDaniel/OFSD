#!/usr/bin/env python
"""Clear cache and force rebuild"""
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from app.Investments.model import PortfolioDisplayCache
from sqlalchemy import text

app = create_app(Config)

with app.app_context():
    print("Clearing portfolio_display_cache...")
    db.session.execute(text("DELETE FROM portfolio_display_cache"))
    db.session.commit()
    print("✅ Cache cleared")
    
    # Verify it's gone
    count = db.session.query(PortfolioDisplayCache).count()
    print(f"Remaining cache records: {count}")
