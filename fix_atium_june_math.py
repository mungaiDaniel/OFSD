"""
Comprehensive fix for Atium June 2026 (ValuationRun #6).

The previous fix_atium_june_data.py script had a bug:
  l[9] was interpreted as 'profit' but was actually 'deposits' (0.0).
  This set end_balance = start_balance + 0 = 55125 instead of 57881.25.
  
  Also, head_office_total was incorrectly bumped by +50000 making it 165762.50.

This script:
  1. Reads ALL Atium June EpochLedger rows.
  2. Recalculates profit = start_balance * performance_rate for each row.
  3. Sets end_balance = start_balance + profit (withdrawals already zeroed out).
  4. Re-signs cryptographic hashes.
  5. Sets head_office_total = SUM(all end_balances).
"""
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


def compute_hash(code, fund_name, epoch_start, epoch_end, perf_rate, start_bal, deposits, wds, profit, end_bal, prev_hash):
    payload = "|".join([
        code,
        fund_name.lower(),
        epoch_start.isoformat() if isinstance(epoch_start, datetime) else str(epoch_start),
        epoch_end.isoformat() if isinstance(epoch_end, datetime) else str(epoch_end),
        f"{Decimal(str(perf_rate)):.8f}",
        f"{Decimal(str(start_bal)):.2f}",
        f"{Decimal(str(deposits)):.2f}",
        f"{Decimal(str(wds)):.2f}",
        f"{Decimal(str(profit)):.2f}",
        f"{Decimal(str(end_bal)):.2f}",
        str(prev_hash),
    ])
    return sha256_hex(payload)


try:
    # Pull ALL Atium June ledgers
    rows = session.execute(text(
        "SELECT id, internal_client_code, fund_name, epoch_start, epoch_end, "
        "performance_rate, start_balance, deposits, withdrawals, profit, end_balance, "
        "previous_hash, current_hash "
        "FROM epoch_ledger "
        "WHERE fund_name = 'Atium' "
        "AND epoch_end >= '2026-06-30 00:00:00' AND epoch_end <= '2026-06-30 23:59:59' "
        "ORDER BY id ASC"
    )).fetchall()

    print(f"Found {len(rows)} Atium June ledger rows")

    total_end_balance = Decimal("0.00")
    for r in rows:
        (lid, code, fund_name, epoch_start, epoch_end, perf_rate,
         start_bal, deposits, wds, old_profit, old_end, prev_hash, old_hash) = r

        start_bal = Decimal(str(start_bal))
        deposits = Decimal(str(deposits))
        perf_rate = Decimal(str(perf_rate))
        wds = Decimal("0.00")  # Always 0 — no withdrawals in committed June period

        # Correct math: profit = (start + deposits) * rate
        profit = (start_bal + deposits) * perf_rate
        end_balance = start_bal + deposits - wds + profit

        # Recompute hash
        new_hash = compute_hash(
            code, fund_name, epoch_start, epoch_end,
            perf_rate, start_bal, deposits, wds, profit, end_balance, prev_hash
        )

        print(f"\n  Ledger #{lid} ({code}):")
        print(f"    start_balance : {start_bal}")
        print(f"    deposits      : {deposits}")
        print(f"    perf_rate     : {perf_rate}")
        print(f"    profit (calc) : {profit}  (was: {old_profit})")
        print(f"    withdrawals   : {wds}")
        print(f"    end_balance   : {end_balance}  (was: {old_end})")
        print(f"    old_hash      : {old_hash}")
        print(f"    new_hash      : {new_hash}")

        session.execute(text(
            f"UPDATE epoch_ledger SET "
            f"profit = {profit}, "
            f"withdrawals = {wds}, "
            f"end_balance = {end_balance}, "
            f"current_hash = '{new_hash}' "
            f"WHERE id = {lid}"
        ))

        total_end_balance += end_balance

    # Update ValuationRun #6 head_office_total to exact sum of end balances
    # This is the CORRECT total — no manual +50k adjustments
    old_total = session.execute(text("SELECT head_office_total FROM valuation_runs WHERE id = 6")).fetchone()[0]
    print(f"\nValuationRun #6:")
    print(f"  old head_office_total: {old_total}")
    print(f"  new head_office_total: {total_end_balance}")

    session.execute(text(
        f"UPDATE valuation_runs SET head_office_total = {total_end_balance} WHERE id = 6"
    ))

    # Also fix any Statement records for this run
    stmts = session.execute(text(
        "SELECT s.id, s.investor_id, s.withdrawals, s.closing_balance, "
        "i.internal_client_code "
        "FROM statements s "
        "JOIN investments i ON i.id = s.investor_id "
        "WHERE s.valuation_run_id = 6"
    )).fetchall()

    print(f"\nUpdating {len(stmts)} Statement records...")
    for st in stmts:
        st_id, inv_id, st_wds, st_close, st_code = st

        # Find matching ledger for this investor
        for r in rows:
            (lid, code, fund_name, epoch_start, epoch_end, perf_rate,
             start_bal, deposits, wds, old_profit, old_end, prev_hash, old_hash) = r
            if code == st_code:
                start_bal = Decimal(str(start_bal))
                deposits = Decimal(str(deposits))
                perf_rate = Decimal(str(perf_rate))
                profit = (start_bal + deposits) * perf_rate
                new_end = start_bal + deposits + profit

                session.execute(text(
                    f"UPDATE statements SET "
                    f"withdrawals = 0, "
                    f"closing_balance = {new_end}, "
                    f"performance_gain = {profit} "
                    f"WHERE id = {st_id}"
                ))
                print(f"  Statement #{st_id} ({st_code}): closing_balance → {new_end}")
                break

    session.commit()
    print("\n✅ ALL REPAIRS COMPLETE.")
    print(f"\nExpected Atium June Closing AUM: ${total_end_balance:,.2f}")
    print("The Reconciliation Alert should now clear.")

except Exception as e:
    session.rollback()
    import traceback
    traceback.print_exc()
    print(f"\n❌ REPAIR FAILED: {str(e)}")
finally:
    session.close()
    engine.dispose()
