#!/usr/bin/env python
"""Verification script to test batch creation with nullable certificate_number."""

from main import app
from app.Batch.model import Batch
from app.database.database import db

with app.app_context():
    try:
        # Try to create a batch without certificate_number
        test_batch = Batch(
            batch_name="Test Batch - Nullable Certificate",
            certificate_number=None,  # This should work now
            is_active=False,
            duration_days=30
        )
        
        db.session.add(test_batch)
        db.session.commit()
        
        print(f"✅ Successfully created batch with NULL certificate_number")
        print(f"   Batch ID: {test_batch.id}")
        print(f"   Batch Name: {test_batch.batch_name}")
        print(f"   Certificate Number: {test_batch.certificate_number}")
        print(f"   Is Active: {test_batch.is_active}")
        
        # Clean up test batch
        db.session.delete(test_batch)
        db.session.commit()
        print(f"✅ Test batch cleaned up")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.session.rollback()
