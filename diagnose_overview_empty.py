#!/usr/bin/env python3
"""
Diagnostic script to identify why the dashboard overview is empty.
"""
import sys
sys.path.insert(0, '/c/Users/Dantez/Documents/results/ofds/backend')

from config import DevelopmentConfig
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# Create app and init db
app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

from app.database.database import db
db.init_app(app)

with app.app_context():
    print("\n" + "="*70)
    print("DASHBOARD OVERVIEW DIAGNOSTIC")
    print("="*70)
    
    # 1. Check CoreFund
    print("\n1. COREFUND (Funds)")
    funds = db.session.execute(text("""
        SELECT id, fund_name, fund_code, is_active FROM core_fund ORDER BY id
    """)).fetchall()
    if funds:
        print(f"   Found {len(funds)} fund(s):")
        for f in funds:
            print(f"     - {f[1]} ({f[2]}) - ID: {f[0]}, Active: {f[3]}")
    else:
        print("   ❌ NO FUNDS FOUND - This is a problem!")
        print("      The dashboard needs at least one active CoreFund")
    
    # 2. Check ShareClass
    print("\n2. SHARECLASS (Fund Classes)")
    classes = db.session.execute(text("""
        SELECT id, core_fund_id, class_name, class_code, currency, is_active 
        FROM share_class ORDER BY core_fund_id, id
    """)).fetchall()
    if classes:
        print(f"   Found {len(classes)} share class(es):")
        for c in classes:
            print(f"     - {c[2]} ({c[4]}) - ID: {c[0]}, Fund ID: {c[1]}, Active: {c[5]}")
    else:
        print("   ❌ NO SHARE CLASSES - This is a problem!")
        print("      Each fund needs at least one active ShareClass (KES or USD)")
    
    # 3. Check NavHistory
    print("\n3. NAVHISTORY (NAV per Share)")
    nav_history = db.session.execute(text("""
        SELECT share_class_id, nav_per_share, nav_date FROM nav_history 
        ORDER BY share_class_id, nav_date DESC LIMIT 10
    """)).fetchall()
    if nav_history:
        print(f"   Found {len(nav_history)} NAV record(s):")
        for n in nav_history:
            print(f"     - Share Class {n[0]}: NAV={n[1]}, Date: {n[2]}")
    else:
        print("   ❌ NO NAV HISTORY - This is CRITICAL!")
        print("      The dashboard displays NAV data from nav_history")
        print("      You need to create NAV records for each share class")
    
    # 4. Check InvestorShares
    print("\n4. INVESTORSHARES (Share Ownership)")
    investor_shares = db.session.execute(text("""
        SELECT share_class_id, COUNT(*) as investor_count, SUM(shares_issued) as total_shares 
        FROM investor_shares 
        GROUP BY share_class_id
    """)).fetchall()
    if investor_shares:
        print(f"   Found share ownership in {len(investor_shares)} class(es):")
        for s in investor_shares:
            print(f"     - Share Class {s[0]}: {s[1]} investor(s), {s[2]} total shares")
    else:
        print("   ⚠️  NO INVESTOR SHARES - Dashboard shows 0 active investors")
        print("      You need investor_shares records when investors have holdings")
    
    # 5. Check ValuationSnapshot
    print("\n5. VALUATIONSNAPSHOT (Performance Data)")
    val_snap = db.session.execute(text("""
        SELECT share_class_id, performance_pct, valuation_date 
        FROM valuation_snapshot 
        ORDER BY share_class_id, valuation_date DESC LIMIT 5
    """)).fetchall()
    if val_snap:
        print(f"   Found {len(val_snap)} valuation snapshot(s):")
        for v in val_snap:
            print(f"     - Share Class {v[0]}: Perf={v[1]}%, Date: {v[2]}")
    else:
        print("   ⚠️  NO VALUATION SNAPSHOTS")
        print("      Performance percentages won't display without these")
    
    # 6. Check Batch
    print("\n6. BATCH (Investment Batches)")
    batches = db.session.execute(text("""
        SELECT id, batch_name, fund_id, is_open, is_active FROM batch ORDER BY id
    """)).fetchall()
    if batches:
        print(f"   Found {len(batches)} batch(es):")
        for b in batches:
            print(f"     - {b[1]} - ID: {b[0]}, Fund: {b[2]}, Open: {b[3]}, Active: {b[4]}")
    else:
        print("   ⚠️  NO BATCHES - Dashboard shows 0 open batches")
    
    # 7. Check Investment
    print("\n7. INVESTMENT (Investor Deposits)")
    investments = db.session.execute(text("""
        SELECT batch_id, COUNT(*) as count, SUM(amount_invested) as total 
        FROM investment 
        GROUP BY batch_id
    """)).fetchall()
    if investments:
        print(f"   Found investments in {len(investments)} batch(es):")
        for inv in investments:
            print(f"     - Batch {inv[0]}: {inv[1]} investor(s), {inv[2]} total invested")
    else:
        print("   ⚠️  NO INVESTMENTS - Dashboard shows 0 active investors")
    
    # 8. Check EpochLedger (Latest committed data)
    print("\n8. EPOCHLEDGER (Latest AUM Data)")
    epoch_ledger = db.session.execute(text("""
        SELECT fund_name, epoch_end, end_balance 
        FROM epoch_ledger 
        ORDER BY fund_name, epoch_end DESC LIMIT 5
    """)).fetchall()
    if epoch_ledger:
        print(f"   Found {len(epoch_ledger)} ledger record(s):")
        for e in epoch_ledger:
            print(f"     - {e[0]}: Epoch {e[1]}, Balance: {e[2]}")
    else:
        print("   ⚠️  NO EPOCH LEDGER - Dashboard shows no historical AUM data")
    
    # SUMMARY
    print("\n" + "="*70)
    print("SUMMARY & RECOMMENDATIONS:")
    print("="*70)
    
    issues = []
    if not funds:
        issues.append("❌ CRITICAL: No CoreFund records exist")
    if not classes:
        issues.append("❌ CRITICAL: No ShareClass records exist")
    if not nav_history:
        issues.append("❌ CRITICAL: No NavHistory records - dashboard needs NAV data")
    if not investments:
        issues.append("⚠️  No investments found")
    if not investor_shares:
        issues.append("⚠️  No investor shares - active investor count will be 0")
    if not val_snap:
        issues.append("⚠️  No ValuationSnapshot - performance % won't display")
    if not epoch_ledger:
        issues.append("⚠️  No EpochLedger - AUM history won't display")
    
    if issues:
        for issue in issues:
            print(f"  {issue}")
    
    print("\nNEXT STEPS:")
    print("  1. Check if funds/share classes exist but are not active")
    print("  2. Create NavHistory for active share classes")
    print("  3. Ensure investors have InvestorShares records")
    print("  4. Run valuation to create ValuationSnapshot and EpochLedger")
    print("\n")
