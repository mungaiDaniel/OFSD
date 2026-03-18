#!/usr/bin/env python3
"""
Final Verification Script - Check that all migrations worked
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import DevelopmentConfig
from app.database.database import db
from flask import Flask
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)
db.init_app(app)

with app.app_context():
    try:
        # Test database connection
        result = db.session.execute(text('SELECT 1')).scalar()
        print('✓ Database connection: OK')
        
        # Check withdrawal fund_id column
        check_sql = """SELECT EXISTS(
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'withdrawals' AND column_name = 'fund_id'
        );"""
        has_column = db.session.execute(text(check_sql)).scalar()
        print('✓ Withdrawal fund_id column: ' + ('EXISTS ✓' if has_column else 'MISSING ✗'))
        
        # Count withdrawals
        count = db.session.execute(text('SELECT COUNT(*) FROM withdrawals;')).scalar()
        print(f'✓ Withdrawals in database: {count}')
        
        # Count core funds
        fund_count = db.session.execute(text('SELECT COUNT(*) FROM core_funds;')).scalar()
        print(f'✓ Core funds in database: {fund_count}')
        
        # Check batches columns
        check_batch = """SELECT EXISTS(
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'batches' AND column_name = 'is_transferred'
        );"""
        has_batch_col = db.session.execute(text(check_batch)).scalar()
        print(f'✓ Batch is_transferred column: ' + ('EXISTS ✓' if has_batch_col else 'MISSING ✗'))
        
        print()
        if has_column and has_batch_col:
            print('✓✓✓ ALL MIGRATIONS VERIFIED - DATABASE IS READY ✓✓✓')
            sys.exit(0)
        else:
            print('✗ Some migrations may be missing')
            sys.exit(1)
        
    except Exception as e:
        print(f'✗ Database error: {str(e)}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
