#!/usr/bin/env python
"""Verification script to check database migration and Flask app connectivity."""

from main import app
from app.Batch.model import Batch
from app.database.database import db

with app.app_context():
    try:
        # Test database connection
        batches = Batch.query.first()
        if batches:
            print(f"✅ Database connection successful")
            print(f"   First batch: {batches.batch_name} (ID: {batches.id})")
            print(f"   is_transferred value: {batches.is_transferred}")
        else:
            print("✅ Database connection successful (no batches found in database)")
        
        print("\n✅ All systems verified successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
