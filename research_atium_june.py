import json
from datetime import datetime
from decimal import Decimal
from app.database.database import db
from app.Valuation.model import ValuationRun, Statement
from app.Investments.model import EpochLedger, Withdrawal
from app.Batch.core_fund import CoreFund
from main import app

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError

with app.app_context():
    fund = db.session.query(CoreFund).filter(CoreFund.fund_name == 'Atium').first()
    if not fund:
        print(json.dumps({"error": "Fund 'Atium' not found"}))
        exit()
        
    run = db.session.query(ValuationRun).filter(
        ValuationRun.core_fund_id == fund.id, 
        ValuationRun.epoch_end == '2026-06-30'
    ).first()
    
    if not run:
        print(json.dumps({"error": "ValuationRun not found for Atium 2026-06-30"}))
        exit()
        
    ledgers = db.session.query(EpochLedger).filter(
        EpochLedger.fund_name == 'Atium', 
        EpochLedger.epoch_end == '2026-06-30', 
        EpochLedger.withdrawals == 50000
    ).all()
    
    statements = db.session.query(Statement).filter(
        Statement.valuation_run_id == run.id, 
        Statement.withdrawals == 50000
    ).all()
    
    wds = db.session.query(Withdrawal).filter(
        Withdrawal.amount == 50000, 
        Withdrawal.fund_name == 'Atium', 
        Withdrawal.status == 'Approved'
    ).all()
    
    data = {
        "run": {
            "id": run.id,
            "epoch_start": run.epoch_start,
            "epoch_end": run.epoch_end,
            "head_office_total": run.head_office_total,
            "status": run.status
        },
        "ledgers": [
            {
                "id": l.id,
                "internal_client_code": l.internal_client_code,
                "withdrawals": l.withdrawals,
                "end_balance": l.end_balance,
                "current_hash": l.current_hash,
                "previous_hash": l.previous_hash
            } for l in ledgers
        ],
        "statements": [
            {
                "id": s.id,
                "investor_id": s.investor_id,
                "withdrawals": s.withdrawals,
                "closing_balance": s.closing_balance
            } for s in statements
        ],
        "withdrawals": [
            {
                "id": w.id,
                "internal_client_code": w.internal_client_code,
                "date_withdrawn": w.date_withdrawn
            } for w in wds
        ]
    }
    
    with open('research_atium_june.json', 'w') as f:
        json.dump(data, f, default=decimal_default, indent=2)
    print("Data saved to research_atium_june.json")
