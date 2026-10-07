#!/usr/bin/env python
"""
Query Audit Logs from Development Database
Displays all audit logs created in the application
"""

import os
import sys
from datetime import datetime, timezone
from app.database.database import db
from app.utils.audit_log import AuditLog
from config import DevelopmentConfig
from main import create_app

# Use development config
app = create_app(DevelopmentConfig)

def query_audit_logs(limit=50):
    """Query and display audit logs"""
    with app.app_context():
        logs = db.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
        
        if not logs:
            print("No audit logs found in database.")
            return
        
        print(f"\n{'='*120}")
        print(f"Audit Logs (Last {limit} entries)")
        print(f"{'='*120}\n")
        
        for log in logs:
            print(f"ID: {log.id}")
            print(f"Action: {log.action}")
            print(f"Target: {log.target_type}#{log.target_id} ({log.target_name})")
            print(f"User: {log.user_id}")
            print(f"IP Address: {log.ip_address}")
            print(f"Timestamp: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"Success: {log.success}")
            if log.description:
                print(f"Description: {log.description}")
            if log.error_message:
                print(f"Error: {log.error_message}")
            print("-" * 120)

def query_by_action(action, limit=20):
    """Query logs by specific action"""
    with app.app_context():
        logs = db.session.query(AuditLog).filter_by(action=action).order_by(AuditLog.timestamp.desc()).limit(limit).all()
        
        if not logs:
            print(f"No logs found for action: {action}")
            return
        
        print(f"\n{'='*120}")
        print(f"Audit Logs for Action: {action}")
        print(f"{'='*120}\n")
        
        for log in logs:
            print(f"[{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {log.target_type}#{log.target_id} - {log.target_name}")

def query_by_target(target_type, target_id):
    """Query logs for specific target"""
    with app.app_context():
        logs = db.session.query(AuditLog).filter_by(
            target_type=target_type,
            target_id=target_id
        ).order_by(AuditLog.timestamp.desc()).all()
        
        if not logs:
            print(f"No logs found for {target_type}#{target_id}")
            return
        
        print(f"\n{'='*120}")
        print(f"Audit Trail: {target_type}#{target_id}")
        print(f"{'='*120}\n")
        
        for log in logs:
            print(f"[{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {log.action} by User#{log.user_id}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'action' and len(sys.argv) > 2:
            query_by_action(sys.argv[2])
        elif command == 'target' and len(sys.argv) > 3:
            query_by_target(sys.argv[2], int(sys.argv[3]))
        else:
            query_audit_logs()
    else:
        query_audit_logs()
