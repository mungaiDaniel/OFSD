#!/usr/bin/env python3
"""
Initialize the database schema and add sample data for the dashboard.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DevelopmentConfig
from flask import Flask
from app.database.database import db

print("=" * 70)
print("DATABASE INITIALIZATION")
print("=" * 70)

# Create Flask app
app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

print(f"\n✓ Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

# Initialize database
db.init_app(app)

with app.app_context():
    try:
        # Test connection
        print("\nTesting database connection...")
        from sqlalchemy import text
        result = db.session.execute(text("SELECT 1"))
        print("✓ Database connection successful")
        
        # Create all tables
        print("\nCreating database schema...")
        db.create_all()
        print("✓ Database schema created successfully")
        
        # Import models to check what was created
        from app.models import CoreFund, ShareClass, NavHistory, InvestorShares, Batch, Investment
        
        # Check if we have any data
        funds = CoreFund.query.all()
        print(f"\n✓ Database ready. Current state:")
        print(f"  - Funds: {len(funds)}")
        print(f"  - Share Classes: {len(ShareClass.query.all())}")
        print(f"  - Batches: {len(Batch.query.all())}")
        print(f"  - Investments: {len(Investment.query.all())}")
        
        if len(funds) == 0:
            print("\n⚠️  No funds found. Dashboard will appear empty until funds and data are added.")
            print("   You need to:")
            print("   1. Create funds via the Admin UI")
            print("   2. Create share classes for each fund")
            print("   3. Add investor data")
            print("   4. Run a valuation to generate NAV and performance data")
        
        print("\n✓ Database initialization complete!\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure PostgreSQL is running")
        print("  2. Check the database credentials in config.py")
        print("  3. Verify the database exists (create it if needed)")
        print("  4. Check your PostgreSQL connection: psql -U postgres -h localhost")
        sys.exit(1)
