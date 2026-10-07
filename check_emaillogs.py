#!/usr/bin/env python
"""Quick diagnostic to check EmailLog records in database"""
import sys
sys.path.insert(0, 'C:\\Users\\Dantez\\Downloads\\ofds\\backend')

from app.database.database import db
from app.Investments.model import EmailLog
from config import DevelopmentConfig as Config
from main import create_app

app = create_app(Config)
with app.app_context():
    # Check all EmailLog records
    all_logs = db.session.query(EmailLog).all()
    print(f"\n📧 Total EmailLog records in database: {len(all_logs)}\n")
    
    if all_logs:
        print("Recent 10 records:")
        for i, log in enumerate(sorted(all_logs, key=lambda x: x.timestamp, reverse=True)[:10], 1):
            print(f"{i}. {log.timestamp} | Status: {log.status} | Type: {log.email_type} | Batch: {log.batch_id} | Investor: {log.investor_id}")
    
    # Check by status
    print("\n📊 Records by status:")
    for status in ['Sent', 'Summary', 'Failed']:
        count = db.session.query(EmailLog).filter(EmailLog.status == status).count()
        print(f"  Status='{status}': {count} records")
    
    # Check DEPOSIT_CONFIRMATION emails
    deposit_logs = db.session.query(EmailLog).filter(EmailLog.email_type == 'DEPOSIT_CONFIRMATION').all()
    print(f"\n💰 DEPOSIT_CONFIRMATION emails: {len(deposit_logs)} records")
    if deposit_logs:
        for log in sorted(deposit_logs, key=lambda x: x.timestamp, reverse=True)[:5]:
            print(f"   {log.timestamp} | Status: {log.status} | Batch: {log.batch_id}")
