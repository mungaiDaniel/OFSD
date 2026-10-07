#!/usr/bin/env python3
"""Diagnostic script to check batch history data"""
import sys
sys.path.insert(0, '/app' if __name__ == '__main__' else '.')

from app.database.database import db
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger
from app.Valuation.model import ValuationRun
from main import create_app
from config import DevelopmentConfig as Config

app = create_app(Config)
with app.app_context():
    # Check Batch 1
    batch = db.session.query(Batch).filter(Batch.id == 1).first()
    print(f"\n{'='*60}")
    print(f"BATCH 1 DIAGNOSTIC")
    print(f"{'='*60}")
    
    if not batch:
        print("❌ Batch 1 not found!")
        sys.exit(1)
    
    print(f"✓ Batch ID 1: {batch.batch_name}")
    print(f"  - Status: {batch.stage}")
    print(f"  - Date Created: {batch.date_created}")
    
    # Get investments
    investments = db.session.query(Investment).filter(Investment.batch_id == 1).all()
    print(f"\n📊 Investments: {len(investments)} total")
    
    if not investments:
        print("  ⚠️  No investments found in batch!")
        sys.exit(1)
    
    investor_codes = [inv.internal_client_code for inv in investments]
    print(f"  📍 Investor codes: {investor_codes}")
    
    for inv in investments[:5]:  # Show first 5
        print(f"    - {inv.internal_client_code}: {inv.amount_deposited} (valuation: {inv.valuation})")
    
    # Check EpochLedger entries
    epoch_entries = (
        db.session.query(EpochLedger)
        .filter(EpochLedger.internal_client_code.in_(investor_codes))
        .all()
    )
    print(f"\n📈 EpochLedger entries: {len(epoch_entries)} total")
    
    if not epoch_entries:
        print("  ⚠️  NO EPOCH LEDGER DATA FOUND!")
        print("  This is why charts are empty - no valuation history is recorded.")
    else:
        # Show unique epochs
        epochs = set((e.epoch_start, e.epoch_end) for e in epoch_entries)
        print(f"  📅 Unique epochs: {len(epochs)}")
        for epoch_start, epoch_end in sorted(epochs)[:3]:
            print(f"    - {epoch_start.strftime('%Y-%m-%d')} to {epoch_end.strftime('%Y-%m-%d')}")
        
        # Sample a few entries
        print(f"\n  Sample EpochLedger entries (first 3):")
        for i, entry in enumerate(epoch_entries[:3]):
            print(f"    [{i+1}] {entry.internal_client_code}")
            print(f"        Epoch: {entry.epoch_start} to {entry.epoch_end}")
            print(f"        Balance: {entry.start_balance} → {entry.end_balance}")
            print(f"        Profit: {entry.profit}")
    
    # Check ValuationRun entries
    vr_entries = db.session.query(ValuationRun).all()
    print(f"\n🔍 ValuationRun entries: {len(vr_entries)} total")
    if vr_entries:
        print(f"  Epochs covered:")
        for vr in vr_entries[:3]:
            print(f"    - {vr.epoch_start} to {vr.epoch_end}: {vr.performance_rate}")

print(f"\n{'='*60}\n")
