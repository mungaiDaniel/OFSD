#!/usr/bin/env python
"""Check database schema for certificate_number column."""

from main import app
from sqlalchemy import text

with app.app_context():
    from app.database.database import db
    
    try:
        # Query the column information
        result = db.session.execute(
            text("""
                SELECT column_name, is_nullable, data_type
                FROM information_schema.columns
                WHERE table_name = 'batches' AND column_name = 'certificate_number'
            """)
        )
        
        row = result.fetchone()
        if row:
            col_name, is_nullable, data_type = row
            print(f"✅ Column: {col_name}")
            print(f"   Data Type: {data_type}")
            print(f"   Is Nullable: {is_nullable}")
            
            if is_nullable == 'YES':
                print(f"✅ Migration successful - certificate_number is now NULLABLE")
            else:
                print(f"❌ Migration failed - certificate_number is still NOT NULL")
        else:
            print("❌ Column not found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
