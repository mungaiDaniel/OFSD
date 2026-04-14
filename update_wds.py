#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from config import DevelopmentConfig as Config
from app.database.database import db
from flask import Flask
from sqlalchemy import text
from decimal import Decimal
import traceback

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    print("--- UPDATING WITHDRAWALS ---")
    
    try:
        # Update Jane Doe's Axiom ($4000) to Completed
        db.session.execute(text("UPDATE withdrawals SET status = 'Completed' WHERE internal_client_code = 'AXIOM-002' AND amount = 4000"))
        
        # Update all other Approved to Processed
        db.session.execute(text("UPDATE withdrawals SET status = 'Processed' WHERE status = 'Approved'"))
        
        db.session.commit()
        print("Updated Jane Doe to Completed, and all other Approved to Processed.")
    except Exception as e:
        print(f"Error updating: {e}")
        db.session.rollback()

    print("\n--- CALCULATING AUM FOR DASHBOARD ---")
    try:
        # We emulate get_base_stats() AUM logic using SQL directly
        # 1. Total End Balance from latest committed epoch ledgers
        latest_sql = text("""
        WITH latest_ledgers AS (
            SELECT internal_client_code, lower(fund_name) as fund_lower, MAX(epoch_end) as max_end
            FROM epoch_ledger
            GROUP BY internal_client_code, lower(fund_name)
        )
        SELECT el.internal_client_code, lower(el.fund_name) as fund_lower, el.end_balance
        FROM epoch_ledger el
        JOIN latest_ledgers ll 
          ON el.internal_client_code = ll.internal_client_code 
          AND lower(el.fund_name) = ll.fund_lower 
          AND el.epoch_end = ll.max_end
        """)
        ledgers = db.session.execute(latest_sql).fetchall()
        
        total_aum = 0.0
        for l in ledgers:
            code = l[0]
            fund_lower = l[1]
            end_bal = float(l[2])
            
            # 2. Total Captured Withdrawals
            captured_sql = text("""
            SELECT COALESCE(SUM(withdrawals), 0)
            FROM epoch_ledger
            WHERE internal_client_code = :code AND lower(fund_name) = :fund
            """)
            captured = float(db.session.execute(captured_sql, {"code": code, "fund": fund_lower}).scalar() or 0)
            
            # 3. Total Approved Withdrawals
            approved_sql = text("""
            SELECT COALESCE(SUM(amount), 0)
            FROM withdrawals
            WHERE internal_client_code = :code AND lower(fund_name) = :fund AND status IN ('Approved', 'Processed', 'Completed')
            """)
            approved = float(db.session.execute(approved_sql, {"code": code, "fund": fund_lower}).scalar() or 0)
            
            uncaptured = max(0.0, approved - captured)
            total_aum += (end_bal - uncaptured)
            
        print(f"Calculated Total AUM: ${total_aum:,.2f}")
        expected_total_aum = 224622.00
        print(f"Expected: ${expected_total_aum:,.2f} -> Diff: ${total_aum - expected_total_aum:,.2f}")
    except Exception as e:
        print("Error evaluating AUM:")
        traceback.print_exc()
