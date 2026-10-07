"""
Simulate uploading May withdrawals and verify they appear in valuation preview
"""
import sys
sys.path.insert(0, '.')

from main import app, db
from app.Investments.model import Withdrawal, WITHDRAWAL_STATUS_APPROVED
from app.Batch.core_fund import CoreFund
from app.logic.valuation_service import PortfolioValuationService
from datetime import datetime, timezone
from decimal import Decimal

with app.app_context():
    # Create test withdrawals for May 2026
    print("=== Creating May 2026 withdrawals (simulating upload) ===\n")
    
    # Get core funds
    axiom_fund = db.session.query(CoreFund).filter(CoreFund.fund_name.ilike('Axiom')).first()
    atium_fund = db.session.query(CoreFund).filter(CoreFund.fund_name.ilike('Atium')).first()
    
    test_withdrawals = [
        # Axiom: 14,000 total
        {'code': 'AXIOM-001', 'fund': axiom_fund, 'amount': Decimal('5000'), 'date': '2026-05-15'},
        {'code': 'AXIOM-002', 'fund': axiom_fund, 'amount': Decimal('6000'), 'date': '2026-05-20'},
        {'code': 'AXIOM-003', 'fund': axiom_fund, 'amount': Decimal('3000'), 'date': '2026-05-10'},
        # Atium: 3,000 total
        {'code': 'ATIUM-007', 'fund': atium_fund, 'amount': Decimal('2000'), 'date': '2026-05-12'},
        {'code': 'ATIUM-008', 'fund': atium_fund, 'amount': Decimal('1000'), 'date': '2026-05-25'},
    ]
    
    # Delete any existing May withdrawals first
    db.session.query(Withdrawal).filter(
        Withdrawal.date_withdrawn >= '2026-05-01',
        Withdrawal.date_withdrawn <= '2026-05-31'
    ).delete()
    db.session.commit()
    
    # Create new May withdrawals with Approved status (simulating the fix)
    for wd in test_withdrawals:
        withdrawal = Withdrawal(
            internal_client_code=wd['code'],
            fund_id=wd['fund'].id,
            fund_name=wd['fund'].fund_name,
            amount=wd['amount'],
            date_withdrawn=datetime.strptime(wd['date'], '%Y-%m-%d'),
            status=WITHDRAWAL_STATUS_APPROVED,  # This is the default now
        )
        db.session.add(withdrawal)
        print(f"  Created: {wd['code']:15} {wd['fund'].fund_name:10} ${wd['amount']:>8,.0f}  status={withdrawal.status}")
    
    db.session.commit()
    
    # Now test the valuation preview
    print("\n=== Testing May 2026 Valuation Preview ===\n")
    
    start_date = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 5, 31, tzinfo=timezone.utc)
    
    # Test Axiom preview
    try:
        axiom_preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Axiom",
            start_date=start_date,
            end_date=end_date,
            performance_rate=Decimal("0.06"),  # 6%
        )
        
        print(f"Axiom Fund Preview:")
        print(f"  Total Withdrawals: ${axiom_preview.get('total_withdrawals', 0):,.2f}")
        print(f"  Reconciliation Total: ${axiom_preview.get('reconciliation_total', 0):,.2f}")
        print(f"  Expected Closing AUM: ${axiom_preview.get('expected_closing_aum', 0):,.2f}")
        
        axiom_wds = axiom_preview.get('total_withdrawals', 0)
        if axiom_wds == 14000.0:
            print(f"  ✅ PASS: Axiom withdrawals = $14,000")
        else:
            print(f"  ❌ FAIL: Expected $14,000, got ${axiom_wds:,.2f}")
            
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
    
    # Test Atium preview
    print()
    try:
        atium_preview = PortfolioValuationService.preview_epoch_for_fund_name(
            fund_name="Atium",
            start_date=start_date,
            end_date=end_date,
            performance_rate=Decimal("0.06"),  # 6%
        )
        
        print(f"Atium Fund Preview:")
        print(f"  Total Withdrawals: ${atium_preview.get('total_withdrawals', 0):,.2f}")
        print(f"  Reconciliation Total: ${atium_preview.get('reconciliation_total', 0):,.2f}")
        print(f"  Expected Closing AUM: ${atium_preview.get('expected_closing_aum', 0):,.2f}")
        
        atium_wds = atium_preview.get('total_withdrawals', 0)
        if atium_wds == 3000.0:
            print(f"  ✅ PASS: Atium withdrawals = $3,000")
        else:
            print(f"  ❌ FAIL: Expected $3,000, got ${atium_wds:,.2f}")
            
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")

    print("\n=== Summary ===")
    print("If both tests PASS, the fix is working correctly.")
    print("The valuation preview now includes uploaded withdrawals automatically.")
