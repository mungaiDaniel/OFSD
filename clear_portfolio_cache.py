#!/usr/bin/env python
"""
Clear the portfolio display cache to force rebuild with corrected calculations
"""
import os
from main import create_app
from config import DevelopmentConfig as Config
from app.database.database import db
from sqlalchemy import text

os.environ.setdefault('FLASK_ENV', 'development')

app = create_app(Config)

with app.app_context():
    try:
        # Clear all cached portfolio display data
        result = db.session.execute(text("DELETE FROM portfolio_display_cache"))
        db.session.commit()
        
        affected_rows = result.rowcount
        print(f"✅ Successfully cleared {affected_rows} cache records")
        print("\n🔄 Cache will be rebuilt on next API request")
        print("📌 Expected to see:")
        print("   - B001: Balance $30,390.85 (not $30,420.26)")
        print("   - B001: Profit $885.17 (not $914.58)")
        print("   - B001: Performance 3.00% (not 3.10%)")
        print("   - B002: Independent values (not affected by B001)")
        
    except Exception as e:
        print(f"❌ Error clearing cache: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
