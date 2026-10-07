#!/usr/bin/env python3
"""
Seed the local dev database from investments_export + valuations_export CSVs.

Wipes existing transactional data (investments, batches, funds, share classes,
epoch ledger, investor shares, NAV history, valuation runs/snapshots, batch
valuations, withdrawals, email logs, statements, portfolio cache) and rebuilds
it from the two CSV exports. Leaves `user` and `audit_logs` untouched.

Usage:
    python seed_from_export.py <investments_csv> <valuations_csv>
"""
import sys
import os
import csv
import hashlib
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

GENESIS_HASH = "0" * 64


def parse_date(s):
    s = (s or "").strip()
    if not s or s in ("—", "-", ""):
        return None
    return datetime.strptime(s, "%m/%d/%Y")


def parse_num(s):
    s = (s or "").strip().replace(",", "")
    if not s or s in ("—", "-", ""):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_pct(s):
    s = (s or "").strip().replace("%", "")
    if not s:
        return Decimal("0")
    return Decimal(s) / Decimal("100")


def sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ledger_hash_payload(*, code, fund_name, epoch_start, epoch_end, performance_rate,
                         start_balance, deposits, withdrawals, profit, end_balance, previous_hash):
    # Field order MUST match app.logic.valuation_service._ledger_hash_payload exactly
    # so /reports/verify-hash-chain/<code>/<fund> can independently recompute and verify.
    return "|".join([
        code,
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
    ])


def main(investments_csv, valuations_csv):
    from main import app
    from app.database.database import db
    from app.Batch.model import Batch
    from app.Batch.core_fund import CoreFund
    from app.Funds.share_class import ShareClass
    from app.Investments.model import (
        Investment, EpochLedger, Withdrawal, EmailLog, PendingEmail, PortfolioDisplayCache,
    )
    from app.Funds.investor_shares import InvestorShares
    from app.Funds.nav_history import NavHistory
    from app.Valuation.model import ValuationRun, BatchValuation
    from app.Valuation.valuation_snapshot import ValuationSnapshot

    with app.app_context():
        session = db.session

        # ── Load CSVs ──
        with open(investments_csv, newline="", encoding="utf-8-sig") as f:
            inv_rows = list(csv.DictReader(f))
        with open(valuations_csv, newline="", encoding="utf-8-sig") as f:
            val_rows = list(csv.DictReader(f))

        print(f"Loaded {len(inv_rows)} investment rows, {len(val_rows)} valuation rows")

        # ── 1. Wipe existing transactional data (FK-safe order) ──
        print("\n[1/9] Wiping existing transactional data...")
        for model in [
            ValuationSnapshot, InvestorShares, NavHistory, EpochLedger,
            BatchValuation, ValuationRun,
            Withdrawal, EmailLog, PendingEmail, PortfolioDisplayCache,
            Investment, Batch, ShareClass, CoreFund,
        ]:
            n = session.query(model).delete()
            print(f"  deleted {n} from {model.__tablename__}")
        session.flush()

        # ── 2. Core funds ──
        print("\n[2/9] Creating core funds...")
        axiom = CoreFund(fund_name="AXIOM AFRICA EQUITY FUND", fund_code="AXM-AFRI", is_active=True)
        dangote = CoreFund(fund_name="Dangote Petroleum Refinery and Petrochemicals FZE", fund_code="DANGPRP", is_active=True)
        session.add_all([axiom, dangote])
        session.flush()

        # ── 3. Share classes ──
        print("[3/9] Creating share classes...")
        classes = {
            "USD_I": ShareClass(core_fund_id=axiom.id, class_name="Axiom USD Class I", class_code="USD_I", currency="USD", is_active=True),
            "KES_I": ShareClass(core_fund_id=axiom.id, class_name="Axiom KES Class I", class_code="KES_I", currency="KES", is_active=True),
            "USD_R": ShareClass(core_fund_id=axiom.id, class_name="Axiom USD Class R", class_code="USD_R", currency="USD", is_active=True),
            "DPRP": ShareClass(core_fund_id=dangote.id, class_name="Dangote DPRP Class", class_code="DPRP", currency="USD", is_active=True),
        }
        session.add_all(classes.values())
        session.flush()

        fund_by_name = {
            "AXIOM AFRICA EQUITY FUND": axiom,
            "Dangote Petroleum Refinery and Petrochemicals FZE": dangote,
        }

        # ── 4. Parse investment rows ──
        parsed_inv = []
        for r in inv_rows:
            parsed_inv.append({
                "client_code": r["Client Code"].strip(),
                "name": r["Client Name"].strip(),
                "email": r["Email"].strip(),
                "date_deposited": parse_date(r["Date Deposited"]),
                "amount_deposited": parse_num(r["Amount Deposited"]) or Decimal("0"),
                "date_transferred": parse_date(r["Date Transferred"]),
                "amount_transferred": parse_num(r["Amount Transferred"]),
                "date_deployed": parse_date(r["Date Deployed"]),
                "amount_deployed": parse_num(r["Amount Deployed"]),
                "shares": parse_num(r["Number of Shares"]),
                "fund_name": r["Fund Invested In"].strip(),
                "class_code": r["Share Class"].strip(),
                "currency": r["Currency"].strip(),
                "batch_name": r["Batch Name"].strip(),
            })

        # ── 5. Batches (one per unique Batch Name) ──
        print("[4/9] Creating batches...")
        by_batch = defaultdict(list)
        for row in parsed_inv:
            by_batch[row["batch_name"]].append(row)

        batches = {}
        for batch_name, rows in by_batch.items():
            deployed_rows = [r for r in rows if r["amount_deployed"] is not None and r["shares"] is not None]
            total_shares = sum((r["shares"] for r in deployed_rows), Decimal("0"))
            total_deployed = sum((r["amount_deployed"] for r in deployed_rows), Decimal("0"))
            total_deposited = sum((r["amount_deposited"] for r in rows), Decimal("0"))
            is_deployed = len(deployed_rows) == len(rows) and total_shares > 0

            date_deployed = min((r["date_deployed"] for r in rows if r["date_deployed"]), default=None)
            cls = classes[rows[0]["class_code"]]

            batch = Batch(
                batch_name=batch_name,
                total_principal=total_deposited,
                date_deployed=date_deployed,
                duration_days=30,
                is_active=is_deployed,
                is_transferred=is_deployed,
                deployment_confirmed=is_deployed,
                stage=4 if is_deployed else 1,
                share_class_id=cls.id,
                is_open=not is_deployed,
                total_shares=total_shares if is_deployed else None,
                deployment_nav=(total_deployed / total_shares) if is_deployed and total_shares > 0 else None,
                deployment_total_nav=total_deployed if is_deployed else None,
            )
            session.add(batch)
            batches[batch_name] = batch
        session.flush()
        print(f"  created {len(batches)} batches")

        # ── 6. Investments + InvestorShares ──
        print("[5/9] Creating investments + investor shares...")
        investments_by_key = {}   # (client_code, batch_name) -> Investment
        shares_by_key = {}        # (client_code, batch_name) -> InvestorShares
        shares_owned_by_key = {}  # (client_code, batch_name) -> Decimal shares (for NAV math later)

        for row in parsed_inv:
            batch = batches[row["batch_name"]]
            fund = fund_by_name[row["fund_name"]]
            cls = classes[row["class_code"]]

            deployed = row["amount_deployed"] is not None and row["shares"] is not None
            amount_transferred = row["amount_transferred"] if row["amount_transferred"] is not None else row["amount_deposited"]
            amount_deployed = row["amount_deployed"] if deployed else amount_transferred
            transfer_fee = max(row["amount_deposited"] - amount_transferred, Decimal("0"))
            deployment_fee = max(amount_transferred - amount_deployed, Decimal("0")) if deployed else Decimal("0")

            inv = Investment(
                investor_name=row["name"],
                investor_email=row["email"],
                internal_client_code=row["client_code"],
                amount_deposited=row["amount_deposited"],
                deployment_fee_deducted=deployment_fee,
                transfer_fee_deducted=transfer_fee,
                date_deposited=row["date_deposited"],
                date_transferred=row["date_transferred"],
                deposit_date=row["date_deposited"].date() if row["date_deposited"] else None,
                fund_name=row["fund_name"],
                batch_id=batch.id,
                fund_id=fund.id,
                share_class_id=cls.id,
                share_series=row["class_code"],
                currency_type=row["currency"],
                shares_owned=row["shares"] if deployed else None,
                opening_market_value=row["amount_deployed"] if deployed else None,
                previous_nav_price=(row["amount_deployed"] / row["shares"]) if deployed and row["shares"] > 0 else None,
            )
            session.add(inv)
            session.flush()

            key = (row["client_code"], row["batch_name"])
            investments_by_key[key] = inv

            if deployed:
                deployment_nav = row["amount_deployed"] / row["shares"]
                inv_shares = InvestorShares(
                    investment_id=inv.id,
                    share_class_id=cls.id,
                    batch_id=batch.id,
                    shares_owned=row["shares"],
                    deployment_nav=deployment_nav,
                    deployment_date=row["date_deployed"].date(),
                    is_active=True,
                )
                session.add(inv_shares)
                session.flush()
                shares_by_key[key] = inv_shares
                shares_owned_by_key[key] = row["shares"]

        print(f"  created {len(investments_by_key)} investments, {len(shares_by_key)} investor-shares rows")

        # ── 7. Parse valuations CSV up front so we know, per share class, whether real
        #        valuation dates exist before deciding whether a synthetic deployment-date
        #        NAV point is needed for that class (see step 7b below).
        print("[6/9] Parsing valuations...")
        parsed_val = []
        for r in val_rows:
            parsed_val.append({
                "fund_name": r["Fund Name"].strip(),
                "epoch_start": parse_date(r["Epoch Start"]),
                "epoch_end": parse_date(r["Epoch End"]),
                "client_code": r["Client Code"].strip(),
                "batch_name": r["Batch"].strip(),
                "opening": parse_num(r["Opening Balance"]) or Decimal("0"),
                "deposits": parse_num(r["Deposits (+)"]) or Decimal("0"),
                "withdrawals": abs(parse_num(r["Withdrawals (-)"]) or Decimal("0")),
                "performance_rate": parse_pct(r["Performance Rate (%)"]),
                "profit": parse_num(r["Profit (+)"]) or Decimal("0"),
                "closing": parse_num(r["Closing Balance"]) or Decimal("0"),
            })

        classes_with_valuation_data = set()
        for row in parsed_val:
            batch = batches.get(row["batch_name"])
            if batch:
                classes_with_valuation_data.add(batch.share_class_id)

        # ── 7b. NAV history: deployment-source rows ──
        # A share class is valued as a whole, on the same handful of dates, across every
        # client holding it (confirmed against the export: e.g. KES_I was valued on exactly
        # 4 shared dates, USD_I on 6 — never a separate date per client or per batch). Adding
        # one NAV point per individual batch's own deployment date (as this used to do) mixed
        # those one-off dates into the same per-class NAV history the chart reads, producing
        # far more points than the real valuation schedule (12 for KES_I instead of 4). Only
        # classes with zero real valuation rows get a synthetic bootstrap point here, so a
        # class that has never been valued still has a NAV to show instead of nothing.
        print("[6b/9] Creating NAV history (deployment-source bootstrap, valuation-less classes only)...")
        dep_nav_points = defaultdict(list)  # (share_class_id, date) -> [nav, ...]
        for row in parsed_inv:
            if row["amount_deployed"] is None or row["shares"] is None or not row["date_deployed"]:
                continue
            cls = classes[row["class_code"]]
            if cls.id in classes_with_valuation_data:
                continue
            nav = row["amount_deployed"] / row["shares"]
            dep_nav_points[(cls.id, row["date_deployed"].date())].append(nav)

        # Collapse to a single bootstrap point per class: the earliest deployment date,
        # NAV weighted by amount deployed across every batch contributing to that date set.
        bootstrap_points = {}
        for (class_id, d), navs in dep_nav_points.items():
            if class_id not in bootstrap_points or d < bootstrap_points[class_id][0]:
                bootstrap_points[class_id] = (d, navs)
        for class_id, (d, navs) in bootstrap_points.items():
            avg_nav = sum(navs, Decimal("0")) / len(navs)
            session.add(NavHistory(share_class_id=class_id, nav_date=d, nav_per_share=avg_nav, source="deployment"))
        session.flush()
        print(f"  created {len(bootstrap_points)} deployment NAV bootstrap points")

        # ── 8. Build EpochLedger (hash-chained), valuation-source NAV history,
        #        ValuationSnapshot (latest per position), ValuationRun, BatchValuation ──

        print("[8/9] Creating EpochLedger (hash-chained) + valuation NAV history + snapshots...")
        by_client = defaultdict(list)
        for row in parsed_val:
            by_client[row["client_code"]].append(row)

        val_nav_points = defaultdict(list)  # (share_class_id, date) -> [nav,...]
        epoch_count = 0
        for client_code, rows in by_client.items():
            rows.sort(key=lambda r: r["epoch_start"])
            prev_hash = GENESIS_HASH
            for row in rows:
                payload = ledger_hash_payload(
                    code=client_code,
                    fund_name=row["fund_name"],
                    epoch_start=row["epoch_start"],
                    epoch_end=row["epoch_end"],
                    performance_rate=row["performance_rate"],
                    start_balance=row["opening"],
                    deposits=row["deposits"],
                    withdrawals=row["withdrawals"],
                    profit=row["profit"],
                    end_balance=row["closing"],
                    previous_hash=prev_hash,
                )
                current_hash = sha256_hex(payload)
                session.add(EpochLedger(
                    internal_client_code=client_code,
                    fund_name=row["fund_name"],
                    epoch_start=row["epoch_start"],
                    epoch_end=row["epoch_end"],
                    performance_rate=row["performance_rate"],
                    start_balance=row["opening"],
                    deposits=row["deposits"],
                    withdrawals=row["withdrawals"],
                    profit=row["profit"],
                    end_balance=row["closing"],
                    previous_hash=prev_hash,
                    current_hash=current_hash,
                ))
                prev_hash = current_hash
                epoch_count += 1

                key = (client_code, row["batch_name"])
                shares = shares_owned_by_key.get(key)
                if shares and shares > 0:
                    batch = batches.get(row["batch_name"])
                    if batch:
                        val_nav_points[(batch.share_class_id, row["epoch_end"].date())].append(row["closing"] / shares)
        session.flush()
        print(f"  created {epoch_count} epoch ledger rows")

        for (class_id, d), navs in val_nav_points.items():
            avg_nav = sum(navs, Decimal("0")) / len(navs)
            session.add(NavHistory(share_class_id=class_id, nav_date=d, nav_per_share=avg_nav, source="valuation"))
        session.flush()
        print(f"  created {len(val_nav_points)} valuation NAV points")

        # One snapshot per (client_code, batch_name, epoch_end) — i.e. every valuation
        # period in the export, not just the latest. The real commit flow
        # (app/logic/nav_valuation_service.py PortfolioValuationService._create_valuation_snapshot)
        # writes one immutable ValuationSnapshot per investor holding per valuation date and
        # never overwrites history; collapsing to "latest only" (as this used to do) meant
        # every period except the most recent had zero snapshots, which is what made the
        # Reports "Generate & Send" panel come back empty for any period other than the last
        # one — GET /reports/eligible-investors filters ValuationSnapshot.valuation_date by
        # the requested month. Reusing the model's own create_snapshot() factory keeps the
        # market_value / performance_pct math identical to what production actually computes.
        snap_count = 0
        for client_code, rows in by_client.items():
            for row in rows:
                key = (client_code, row["batch_name"])
                inv_shares = shares_by_key.get(key)
                if not inv_shares:
                    continue
                shares = shares_owned_by_key[key]
                nav_per_share = row["closing"] / shares if shares > 0 else Decimal("0")
                session.add(ValuationSnapshot.create_snapshot(
                    investor_shares_id=inv_shares.id,
                    valuation_date=row["epoch_end"].date(),
                    nav_per_share=nav_per_share,
                    shares_held=shares,
                    deployment_nav=inv_shares.deployment_nav,
                ))
                snap_count += 1
        session.flush()
        print(f"  created {snap_count} valuation snapshots")

        # ── 9. ValuationRun + BatchValuation ──
        print("[9/9] Creating valuation runs + batch valuations...")
        by_epoch_end = defaultdict(list)
        for row in parsed_val:
            by_epoch_end[row["epoch_end"]].append(row)

        for epoch_end, rows in by_epoch_end.items():
            epoch_start = min(r["epoch_start"] for r in rows)
            head_office_total = sum((r["closing"] for r in rows), Decimal("0"))
            avg_rate = sum((r["performance_rate"] for r in rows), Decimal("0")) / len(rows)
            session.add(ValuationRun(
                core_fund_id=axiom.id,
                epoch_start=epoch_start,
                epoch_end=epoch_end,
                performance_rate=avg_rate,
                head_office_total=head_office_total,
                status="Committed",
                is_committed=True,
            ))

        by_batch_epoch = defaultdict(list)
        for row in parsed_val:
            batch = batches.get(row["batch_name"])
            if batch:
                by_batch_epoch[(batch.id, row["epoch_end"])].append(row)

        for (batch_id, epoch_end), rows in by_batch_epoch.items():
            balance = sum((r["closing"] for r in rows), Decimal("0"))
            principal = sum((r["opening"] for r in rows), Decimal("0"))
            profit = sum((r["profit"] for r in rows), Decimal("0"))
            withdrawals = sum((r["withdrawals"] for r in rows), Decimal("0"))
            avg_rate = sum((r["performance_rate"] for r in rows), Decimal("0")) / len(rows)
            session.add(BatchValuation(
                batch_id=batch_id,
                period_end_date=epoch_end,
                balance_at_end_of_period=balance,
                performance_rate=avg_rate,
                total_principal=principal,
                total_profit=profit,
                total_withdrawals=withdrawals,
            ))

        session.commit()
        print(f"  created {len(by_epoch_end)} valuation runs, {len(by_batch_epoch)} batch valuations")

        print("\n=== DONE ===")
        print(f"Core funds:        {session.query(CoreFund).count()}")
        print(f"Share classes:     {session.query(ShareClass).count()}")
        print(f"Batches:           {session.query(Batch).count()}")
        print(f"Investments:       {session.query(Investment).count()}")
        print(f"Investor shares:   {session.query(InvestorShares).count()}")
        print(f"NAV history:       {session.query(NavHistory).count()}")
        print(f"Epoch ledger:      {session.query(EpochLedger).count()}")
        print(f"Valuation snaps:   {session.query(ValuationSnapshot).count()}")
        print(f"Valuation runs:    {session.query(ValuationRun).count()}")
        print(f"Batch valuations:  {session.query(BatchValuation).count()}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python seed_from_export.py <investments_csv> <valuations_csv>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
