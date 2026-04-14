import hashlib
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URI = "postgresql://postgres:username@localhost/offshow_dev"
engine = create_engine(DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

def sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def ledger_hash_payload(
    *,
    internal_client_code: str,
    fund_name: str,
    epoch_start: datetime,
    epoch_end: datetime,
    performance_rate: Decimal,
    start_balance: Decimal,
    deposits: Decimal,
    withdrawals: Decimal,
    profit: Decimal,
    end_balance: Decimal,
    previous_hash: str,
) -> str:
    # Match the exact format in app.logic.valuation_service._ledger_hash_payload
    return "|".join(
        [
            internal_client_code,
            fund_name.lower(),
            epoch_start.isoformat(),
            epoch_end.isoformat(),
            f"{performance_rate:.8f}",
            f"{start_balance:.2f}",
            f"{deposits:.2f}",
            f"{withdrawals:.2f}",
            f"{profit:.2f}",
            f"{end_balance:.2f}",
            previous_hash,
        ]
    )

try:
    # 1. Update EpochLedger ID 15 (ATIUM-008)
    print("Repairing EpochLedger #15...")
    l = session.execute(text("SELECT id, internal_client_code, fund_name, epoch_start, epoch_end, performance_rate, start_balance, deposits, withdrawals, profit, end_balance, previous_hash FROM epoch_ledger WHERE id = 15")).fetchone()
    
    # New values: withdrawals=0, end_balance = start+profit (since deposits=0)
    start = Decimal(str(l[8]))
    new_wds = Decimal("0.00")
    perf_rate = Decimal(str(l[5]))
    profit = Decimal(str(l[9])) # Keep existing profit
    new_end = Decimal(str(l[8])) + profit
    
    # Map back the payload exactly
    payload = ledger_hash_payload(
        internal_client_code=l[1],
        fund_name=l[2],
        epoch_start=l[3],
        epoch_end=l[4],
        performance_rate=perf_rate,
        start_balance=start,
        deposits=Decimal(str(l[7])),
        withdrawals=new_wds,
        profit=profit,
        end_balance=new_end,
        previous_hash=l[11]
    )
    new_hash = sha256_hex(payload)
    print(f"  Old hash: {l[10] if len(l) > 10 else 'N/A'}")
    print(f"  New hash: {new_hash}")
    
    session.execute(text(f"UPDATE epoch_ledger SET withdrawals = {new_wds}, end_balance = {new_end}, current_hash = '{new_hash}' WHERE id = 15"))
    
    # 2. Update Statement for investor ATIUM-008 in valuation_run_id 6
    print("Repairing Statement...")
    # Find statement for investor ATIUM-008 (we find its investment ID first)
    inv = session.execute(text("SELECT id FROM investments WHERE internal_client_code = 'ATIUM-008'")).fetchone()
    if inv:
        stmt = session.execute(text(f"SELECT id FROM statements WHERE investor_id = {inv[0]} AND valuation_run_id = 6")).fetchone()
        if stmt:
            session.execute(text(f"UPDATE statements SET withdrawals = 0, closing_balance = {new_end} WHERE id = {stmt[0]}"))
            print(f"  Statement #{stmt[0]} updated.")
        else:
            print("  Statement not found, potentially not created yet.")
    
    # 3. Update ValuationRun ID 6 Total
    print("Updating ValuationRun #6 total...")
    # Add 50000 back to the fund-wide total sum
    session.execute(text("UPDATE valuation_runs SET head_office_total = head_office_total + 50000 WHERE id = 6"))
    
    session.commit()
    print("REPAIR COMPLETE.")
    
except Exception as e:
    session.rollback()
    print(f"REPAIR FAILED: {str(e)}")
finally:
    session.close()
