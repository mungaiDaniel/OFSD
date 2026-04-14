#!/usr/bin/env python3
"""
Direct test of /api/v1/stats/overview endpoint to verify aggregation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from decimal import Decimal
from main import app
from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Batch.model import Batch

def test_endpoint():
    with app.app_context():
        # Get all batches and their data
        print("\n" + "="*80)
        print("DIAGNOSTIC: Database State Before Endpoint Call")
        print("="*80)
        
        batches = db.session.query(Batch).all()
        print(f"\nTotal Batches: {len(batches)}\n")
        
        for batch in batches:
            print(f"📦 Batch ID {batch.id}: {batch.batch_name}")
            
            investments = db.session.query(Investment).filter_by(batch_id=batch.id).all()
            batch_principal = sum(Decimal(str(i.amount_deposited or 0)) for i in investments)
            
            print(f"   Investments: {len(investments)}")
            print(f"   Total Principal: ${float(batch_principal):,.2f}")
            
            # Show investor codes and funds
            for inv in investments:
                print(f"     - {inv.internal_client_code}: ${float(inv.amount_deposited):,.2f} ({inv.fund_name})")
            
            # Check for ledgers
            investor_codes = [i.internal_client_code for i in investments]
            if investor_codes:
                ledgers = db.session.query(EpochLedger).filter(
                    EpochLedger.internal_client_code.in_(investor_codes)
                ).all()
                
                if ledgers:
                    print(f"   ✓ Has committed epochs: {len(set(l.epoch_end for l in ledgers))} unique")
                    latest_epoch = max(l.epoch_end for l in ledgers)
                    print(f"   Latest epoch: {latest_epoch.date()}")
                    
                    ledger_total = sum(Decimal(str(l.end_balance or 0)) for l in ledgers if l.epoch_end == latest_epoch)
                    print(f"   Latest ledger balance: ${float(ledger_total):,.2f}")
                else:
                    print(f"   ✓ No committed epochs (fresh batch)")
        
        # Check withdrawals
        all_wds = db.session.query(Withdrawal).filter(Withdrawal.status.in_(['Approved', 'Processed', 'Completed', 'Executed'])).all()
        if all_wds:
            total_wds = sum(Decimal(str(w.amount or 0)) for w in all_wds)
            print(f"\nTotal Approved Withdrawals: ${float(total_wds):,.2f}")
        
        # Now call the endpoint
        print("\n" + "="*80)
        print("CALLING /api/v1/stats/overview")
        print("="*80)
        
        from flask_jwt_extended import create_access_token
        
        client = app.test_client()
        token = create_access_token(identity="test_user", additional_claims={'admin': 1})
        
        response = client.get(
            '/api/v1/stats/overview',
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            data = response.get_json()
            print(f"\n✅ Response Status: {response.status_code}")
            
            result = data["data"]
            print(f"\n📊 RETURNED VALUES:")
            print(f"   total_aum: ${result['total_aum']:,.2f}")
            print(f"   total_profit: ${result['total_profit']:,.2f}")
            print(f"   total_withdrawals: ${result['total_withdrawals']:,.2f}")
            print(f"   performance_pct: {result['performance_pct']:.2f}%")
            print(f"   total_investors: {result['total_investors']}")
            print(f"   active_batches: {result['active_batches']}")
            
            print(f"\n📈 ALLOCATION DATA:")
            for item in result.get('alloc_data', []):
                print(f"   {item['name']}: ${item['value']:,.2f}")
            
            print(f"\n💱 FLOW SERIES (Deposits/Withdrawals):")
            for point in result.get('flow_series', []):
                print(f"   {point['label']}: Dep ${point['deposits']:,.2f}, Wd ${point['withdrawals']:,.2f}")
            
            # Verify expectation
            print("\n" + "="*80)
            print("VERIFICATION")
            print("="*80)
            expected_aum = Decimal("519071.61")
            actual_aum = Decimal(str(result['total_aum']))
            
            if abs(actual_aum - expected_aum) < Decimal("1.00"):
                print(f"✅ PASS: AUM matches expected ${float(expected_aum):,.2f}")
            else:
                print(f"❌ FAIL: AUM mismatch!")
                print(f"   Expected: ${float(expected_aum):,.2f}")
                print(f"   Actual:   ${float(actual_aum):,.2f}")
                print(f"   Delta:    ${float(actual_aum - expected_aum):,.2f}")
        else:
            print(f"❌ API Error: {response.status_code}")
            print(response.get_json())

if __name__ == '__main__':
    test_endpoint()
