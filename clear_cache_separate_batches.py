#!/usr/bin/env python
"""
Clear portfolio display cache - forces rebuild with SEPARATE batch calculations
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
        print("✅ SUCCESS: Cache cleared!")
        print(f"   Cleared {affected_rows} cache records")
        print()
        print("📌 Expected after refresh:")
        print("   B001 (Jan deployed):")
        print("     Opening:     $29,505.68")
        print("     Balance:     $30,390.85 ✓")
        print("     Profit:      $885.17 ✓")
        print("     Performance: 3.00% ✓")
        print()
        print("   B002 (Feb deployed NEW):")
        print("     Opening:     $29,505.68 (the new principal)")
        print("     Balance:     $29,505.68 (no valuation yet)")
        print("     Profit:      $0.00 (no valuation yet)")
        print("     Performance: 0.00%")
        print()
        print("🔄 Next step: Refresh the browser (Ctrl+F5 or Cmd+Shift+R)")
        print("   to rebuild with SEPARATE batch calculations")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
