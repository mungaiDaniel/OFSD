#!/usr/bin/env python
"""Verify that batch table has nullable constraints."""

from main import app
from sqlalchemy import text

with app.app_context():
    from app.database.database import db
    
    try:
        print("Checking batches table schema...\n")
        
        columns_to_check = [
            'batch_name',
            'certificate_number', 
            'date_deployed',
            'date_closed',
            'is_active'
        ]
        
        for col in columns_to_check:
            result = db.session.execute(
                text(f"""
                    SELECT column_name, is_nullable, data_type, column_default
                    FROM information_schema.columns
                    WHERE table_name = 'batches' AND column_name = '{col}'
                """)
            )
            
            row = result.fetchone()
            if row:
                col_name, is_nullable, data_type, col_default = row
                nullable_status = "✅ NULLABLE" if is_nullable == 'YES' else "❌ NOT NULL"
                default_status = f"(default: {col_default})" if col_default else "(no default)"
                print(f"{col:20} | {nullable_status:15} | {data_type:15} {default_status}")
            else:
                print(f"{col:20} | ❌ NOT FOUND")
        
        print("\n" + "="*70)
        print("✅ Schema verification complete")
        print("="*70)
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
