from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func, text, and_
from decimal import Decimal
from datetime import datetime

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Valuation.model import ValuationRun, Statement
from app.Investments.model import EpochLedger, Withdrawal, Investment, FINAL_WITHDRAWAL_STATUSES

stats_v1 = Blueprint("stats_v1", __name__, url_prefix="/")


def float_2dp(val) -> float:
    if val is None:
        return 0.0
    return float(Decimal(str(val)).quantize(Decimal("0.01")))


@stats_v1.route("/api/v1/stats/overview", methods=["GET"])
@jwt_required()
def get_overview_stats():
    try:
        # ── 1. Find the LATEST committed epoch per investor/fund from the immutable epoch ledger ──
        # This ensures totals reflect the latest finalized closing balances only.
        latest_ledger_per_key_sq = (
            db.session.query(
                EpochLedger.internal_client_code.label("internal_client_code"),
                func.lower(EpochLedger.fund_name).label("fund_lower"),
                func.max(EpochLedger.epoch_end).label("latest_epoch_end"),
            )
            .group_by(EpochLedger.internal_client_code, func.lower(EpochLedger.fund_name))
            .subquery("latest_ledger_per_key")
        )

        latest_rows = (
            db.session.query(
                EpochLedger.internal_client_code,
                EpochLedger.fund_name,
                EpochLedger.start_balance,
                EpochLedger.deposits,
                EpochLedger.withdrawals,
                EpochLedger.profit,
                EpochLedger.end_balance,
                EpochLedger.epoch_end,
            )
            .join(
                latest_ledger_per_key_sq,
                and_(
                    EpochLedger.internal_client_code == latest_ledger_per_key_sq.c.internal_client_code,
                    func.lower(EpochLedger.fund_name) == latest_ledger_per_key_sq.c.fund_lower,
                    EpochLedger.epoch_end == latest_ledger_per_key_sq.c.latest_epoch_end,
                ),
            )
            .all()
        )

        # ── 2. Compute KPIs - NEW APPROACH ──
        # Strategy: Get total AUM by summing batch-level principal contributions
        # Then apply any profit/growth from committed epochs
        
        from app.Batch.model import Batch as BatchModel
        
        # ── CRITICAL: Find the LAST PROCESSED epoch (Sept 2026) ──
        # Only include chart data up to the latest ValuationRun with status="Committed"
        # This prevents unprocessed months (like October in "Principal Only" state) from showing
        max_chart_epoch = db.session.query(
            func.max(ValuationRun.epoch_end)
        ).filter(
            func.lower(ValuationRun.status) == "committed"
        ).scalar()
        
        total_aum = Decimal("0")
        total_profit = Decimal("0")
        total_invested = Decimal("0")
        unique_investors = set()
        latest_epoch_end = None

        # Get all unique investors from ledgers (up to max_chart_epoch only)
        for row in latest_rows:
            # Skip rows beyond the max processed epoch (e.g., October data if only Sept committed)
            if max_chart_epoch and row.epoch_end > max_chart_epoch:
                continue
            total_profit += Decimal(str(row.profit or 0))
            unique_investors.add(row.internal_client_code)
            if latest_epoch_end is None or row.epoch_end > latest_epoch_end:
                latest_epoch_end = row.epoch_end
        
        # Get all investments organized by investor, fund, AND BATCH
        all_investments = db.session.query(
            Investment.id,
            Investment.batch_id,
            Investment.internal_client_code,
            func.lower(func.coalesce(Investment.fund_name, CoreFund.fund_name, "unknown")).label("fund_lower"),
            func.coalesce(Investment.fund_name, CoreFund.fund_name, "unknown").label("fund_name"),
            Investment.amount_deposited,
            Investment.date_deposited.label("date_deposited"),
        ).outerjoin(CoreFund, Investment.fund_id == CoreFund.id).order_by(
            Investment.internal_client_code, Investment.fund_name
        ).all()

        # Identify deployed batches: ones that have at least one investor+fund with a committed ledger
        all_batches = db.session.query(BatchModel).all()
        batch_ids_deployed = set()
        
        for row in latest_rows:
            # Find which batches contain this investor
            investor_batch_ids = set(
                inv.batch_id for inv in all_investments if inv.internal_client_code == row.internal_client_code
            )
            batch_ids_deployed.update(investor_batch_ids)

        # Build principal sums per investor+fund+batch
        investor_fund_batch_principals = {}
        
        for inv in all_investments:
            key = (inv.internal_client_code, inv.fund_lower)
            batch_key = (key, inv.batch_id)
            if batch_key not in investor_fund_batch_principals:
                investor_fund_batch_principals[batch_key] = Decimal("0")
            investor_fund_batch_principals[batch_key] += Decimal(str(inv.amount_deposited or 0))
            unique_investors.add(inv.internal_client_code)

        # Build withdrawal maps
        total_deposits = db.session.query(
            func.coalesce(func.sum(Investment.amount_deposited), 0)
        ).scalar() or 0

        approved_withdrawal_rows = db.session.query(
            Withdrawal.internal_client_code,
            func.lower(func.coalesce(Withdrawal.fund_name, CoreFund.fund_name, "unknown")).label("fund_lower"),
            func.coalesce(func.sum(Withdrawal.amount), 0).label("total_amount")
        ).outerjoin(CoreFund, Withdrawal.fund_id == CoreFund.id).filter(
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
        ).group_by(
            Withdrawal.internal_client_code,
            func.lower(func.coalesce(Withdrawal.fund_name, CoreFund.fund_name, "unknown"))
        ).all()

        approved_wd_map = {
            (row.internal_client_code, row.fund_lower): Decimal(str(row.total_amount or 0))
            for row in approved_withdrawal_rows
        }

        # Now build AUM:
        # For each investor+fund with a ledger: use ledger as the current value
        # For each investor+fund WITHOUT a ledger: use fresh principal
        # Then repeat for EACH batch that investor appears in
        
        fund_alloc_totals = {}
        fund_label_by_lower = {}
        
        # Build fund name map first
        for inv in all_investments:
            fund_lower = inv.fund_lower
            if fund_lower not in fund_label_by_lower:
                fund_label_by_lower[fund_lower] = inv.fund_name

        # Process by investor+fund combo, considering all batch instances
        processed_keys = set()
        
        # Build ledger map
        latest_rows_by_key = {(r.internal_client_code, r.fund_name.lower()): r for r in latest_rows}
        
        for (inv_code, fund_lower) in sorted(set((i.internal_client_code, i.fund_lower) for i in all_investments)):
            key = (inv_code, fund_lower)
            
            if key in latest_rows_by_key:
                # Has ledger: the ledger balance reflects growth from ALL batches for this investor/fund
                ledger = latest_rows_by_key[key]
                current_value = Decimal(str(ledger.end_balance or 0))
                
                # Deduct uncaptured withdrawals
                total_approved_wd = approved_wd_map.get(key, Decimal("0"))
                total_captured_wd = db.session.query(
                    func.coalesce(func.sum(EpochLedger.withdrawals), 0)
                ).filter(
                    EpochLedger.internal_client_code == inv_code,
                    func.lower(EpochLedger.fund_name) == fund_lower
                ).scalar() or 0
                uncaptured_wd = max(Decimal("0"), Decimal(str(total_approved_wd)) - Decimal(str(total_captured_wd)))
                current_value -= uncaptured_wd
                
                # FIX: Add completely fresh un-epoch'ed deposits!
                fresh_deposits = Decimal("0")
                for i in all_investments:
                    if i.internal_client_code == inv_code and i.fund_lower == fund_lower:
                        if i.amount_deposited and i.date_deposited:
                            dep_naive = i.date_deposited.replace(tzinfo=None) if i.date_deposited.tzinfo else i.date_deposited
                            ledger_naive = ledger.epoch_end.replace(tzinfo=None) if ledger.epoch_end.tzinfo else ledger.epoch_end
                            if dep_naive > ledger_naive:
                                fresh_deposits += Decimal(str(i.amount_deposited))
                
                current_value += fresh_deposits
            else:
                # No ledger: sum all fresh principals across all batches
                current_value = Decimal("0")
                for batch_id in set(b.id for b in all_batches):
                    batch_key = (key, batch_id)
                    if batch_key in investor_fund_batch_principals:
                        current_value += investor_fund_batch_principals[batch_key]
                current_value -= approved_wd_map.get(key, Decimal("0"))
            
            total_aum += current_value
            
            # Track for allocation
            if fund_lower not in fund_alloc_totals:
                fund_alloc_totals[fund_lower] = Decimal("0")
            fund_alloc_totals[fund_lower] += current_value

        # For performance calculation, use total of fresh principals from all batches
        total_investments_value = sum(investor_fund_batch_principals.values())
        total_withdrawals_all = db.session.query(
            func.coalesce(func.sum(Withdrawal.amount), 0)
        ).filter(Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)).scalar() or 0
        total_invested = total_investments_value - Decimal(str(total_withdrawals_all))
        total_withdrawals = Decimal(str(total_withdrawals_all))

        performance_pct = 0.0
        if total_invested > 0:
            performance_pct = float(((total_aum - total_invested) / total_invested) * 100)

        # Build allocation data
        alloc_data_list = [
            {"name": fund_label_by_lower.get(fund_lower, fund_lower.title()), "value": float_2dp(value)}
            for fund_lower, value in fund_alloc_totals.items()
        ]

        # ── 3. Active fund count from committed ValuationRuns ──
        active_funds = (
            db.session.query(func.count(func.distinct(ValuationRun.core_fund_id)))
            .filter(ValuationRun.status == "Committed")
            .scalar() or 0
        )

        # ── 4. Flow series — deposits & withdrawals by transaction day ──
        deposit_rows = db.session.query(
            func.extract("year", Investment.date_deposited).label("yr"),
            func.extract("month", Investment.date_deposited).label("mo"),
            func.extract("day", Investment.date_deposited).label("dy"),
            func.coalesce(func.sum(Investment.amount_deposited), 0).label("total_deps")
        ).group_by(
            func.extract("year", Investment.date_deposited),
            func.extract("month", Investment.date_deposited),
            func.extract("day", Investment.date_deposited)
        ).all()

        withdrawal_rows = db.session.query(
            func.extract("year", Withdrawal.date_withdrawn).label("yr"),
            func.extract("month", Withdrawal.date_withdrawn).label("mo"),
            func.extract("day", Withdrawal.date_withdrawn).label("dy"),
            func.coalesce(func.sum(Withdrawal.amount), 0).label("total_wds")
        ).filter(
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
        ).group_by(
            func.extract("year", Withdrawal.date_withdrawn),
            func.extract("month", Withdrawal.date_withdrawn),
            func.extract("day", Withdrawal.date_withdrawn)
        ).all()

        flow_days = {}
        for row in deposit_rows:
            key = (int(row.yr), int(row.mo), int(row.dy))
            flow_days[key] = {
                "date_point": datetime(int(row.yr), int(row.mo), int(row.dy)),
                "total_deps": Decimal(str(row.total_deps or 0)),
                "total_wds": Decimal("0"),
            }

        for row in withdrawal_rows:
            key = (int(row.yr), int(row.mo), int(row.dy))
            day_entry = flow_days.setdefault(key, {
                "date_point": datetime(int(row.yr), int(row.mo), int(row.dy)),
                "total_deps": Decimal("0"),
                "total_wds": Decimal("0"),
            })
            day_entry["total_wds"] += Decimal(str(row.total_wds or 0))

        flow_series = [
            {
                "label": dt.strftime("%b %d"),
                "deposits": float_2dp(data["total_deps"]),
                "withdrawals": float_2dp(data["total_wds"]),
            }
            for _, data in sorted(flow_days.items())
            for dt in [data["date_point"]]
        ]

        # Per-batch deposit datasets (for multi-colored bars in UI).
        deposit_rows_by_batch = (
            db.session.query(
                func.extract("year", Investment.date_deposited).label("yr"),
                func.extract("month", Investment.date_deposited).label("mo"),
                func.extract("day", Investment.date_deposited).label("dy"),
                Investment.batch_id.label("batch_id"),
                BatchModel.batch_name.label("batch_name"),
                func.coalesce(func.sum(Investment.amount_deposited), 0).label("total_deps"),
            )
            .join(BatchModel, BatchModel.id == Investment.batch_id, isouter=True)
            .group_by(
                func.extract("year", Investment.date_deposited),
                func.extract("month", Investment.date_deposited),
                func.extract("day", Investment.date_deposited),
                Investment.batch_id,
                BatchModel.batch_name,
            )
            .all()
        )

        sorted_day_keys = sorted(flow_days.keys())
        flow_labels = [datetime(y, m, d).strftime("%b %d") for (y, m, d) in sorted_day_keys]
        withdrawals_by_label = [float_2dp(flow_days[(y, m, d)]["total_wds"]) for (y, m, d) in sorted_day_keys]

        by_batch = {}
        for row in deposit_rows_by_batch:
            y, m, d = int(row.yr), int(row.mo), int(row.dy)
            label = datetime(y, m, d).strftime("%b %d")
            batch_id = int(row.batch_id) if row.batch_id is not None else 0
            batch_name = row.batch_name or f"Batch {batch_id}"
            bucket = by_batch.setdefault(batch_id, {"batch_id": batch_id, "batch_name": batch_name, "by_label": {}})
            bucket["by_label"][label] = bucket["by_label"].get(label, Decimal("0")) + Decimal(str(row.total_deps or 0))

        flow_by_batch = {
            "labels": flow_labels,
            "batches": [
                {
                    "batch_id": item["batch_id"],
                    "batch_name": item["batch_name"],
                    "deposits": [float_2dp(item["by_label"].get(lbl, Decimal("0"))) for lbl in flow_labels],
                }
                for _, item in sorted(by_batch.items(), key=lambda x: x[0])
            ],
            "withdrawals": withdrawals_by_label,
        }

        # ── 5. Fallback if no committed epochs — read raw investments ──
        if not latest_rows:
            total_deps = db.session.query(
                func.coalesce(func.sum(Investment.amount_deposited), 0)
            ).scalar() or 0
            total_wds = db.session.query(
                func.coalesce(func.sum(Withdrawal.amount), 0)
            ).filter(Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)).scalar() or 0
            total_invs = db.session.query(
                func.count(func.distinct(Investment.internal_client_code))
            ).scalar() or 0
            first_deposit = db.session.query(func.min(Investment.date_deposited)).scalar()
            initial_label = (
                first_deposit.strftime("%b %d") if first_deposit else datetime.now().strftime("%b %d")
            )

            flow_series = [
                {
                    "label": initial_label,
                    "deposits": float_2dp(total_deps),
                    "withdrawals": float_2dp(total_wds),
                }
            ]

            return jsonify({
                "status": 200,
                "data": {
                    "total_aum": float_2dp(Decimal(str(total_deps)) - Decimal(str(total_wds))),
                    "total_profit": 0.0,
                    "total_investors": int(total_invs),
                    "performance_pct": 0.0,
                    "active_batches": 0,
                    "latest_epoch_end": None,
                    "max_chart_epoch": None,
                    "previous_epoch_end": None,
                    "flow_series": flow_series,
                    "flow_by_batch": flow_by_batch,
                    "alloc_data": [],
                    "aum_data": {"labels": ["—"], "funds": []},
                },
            }), 200

        # ── 6. Build aum_data for exact Portfolio AUM line chart ──
        # Fetch all ledgers chronologically, but ONLY up to the latest committed ValuationRun
        history_ledgers = db.session.query(
            EpochLedger.epoch_end,
            func.lower(EpochLedger.fund_name).label("fund_lower"),
            EpochLedger.fund_name,
            func.sum(EpochLedger.end_balance).label("total_end_balance")
        )
        
        # Apply max_chart_epoch filter to exclude unprocessed months
        if max_chart_epoch:
            history_ledgers = history_ledgers.filter(EpochLedger.epoch_end <= max_chart_epoch)
        
        history_ledgers = history_ledgers.group_by(
            EpochLedger.epoch_end, func.lower(EpochLedger.fund_name), EpochLedger.fund_name
        ).order_by(EpochLedger.epoch_end.asc()).all()

        aum_dates_set = sorted(list(set(r.epoch_end for r in history_ledgers)))
        # Keep label format consistent across charts (month + day).
        aum_labels = [d.strftime("%b %d") for d in aum_dates_set]

        fund_names_set = set(r.fund_name for r in history_ledgers)
        
        aum_funds_map = {f: {"name": f, "data": []} for f in fund_names_set}

        for d in aum_dates_set:
            for f in fund_names_set:
                # Find ledger for this date and fund
                row = next((r for r in history_ledgers if r.epoch_end == d and r.fund_name == f), None)
                val = float(row.total_end_balance) if row else 0.0
                
                # If this is the absolute LAST period across the board, apply the uncaptured withdrawal deduction!
                if row and d == latest_epoch_end:
                    # find the fund_uncap we already calculated above
                    correct_val = next((item["value"] for item in alloc_data_list if item["name"] == f), val)
                    val = float(correct_val)
                    
                aum_funds_map[f]["data"].append(val)

        aum_funds_list = []
        for f in fund_names_set:
            data_arr = aum_funds_map[f]["data"]
            growth_arr = [0.0]
            for i in range(1, len(data_arr)):
                prev = data_arr[i-1]
                curr = data_arr[i]
                growth_arr.append(((curr - prev) / prev * 100) if prev > 0 else 0)
            aum_funds_list.append({
                "name": f,
                "data": data_arr,
                "growth": [float_2dp(g) for g in growth_arr]
            })

        aum_data_obj = {
            "labels": aum_labels if aum_labels else ["—"],
            "funds": aum_funds_list if aum_funds_list else [{"name": "No data", "data": [0], "growth": [0]}]
        }

        return jsonify({
            "status": 200,
            "data": {
                "total_aum": float_2dp(total_aum),
                "total_withdrawals": float_2dp(total_withdrawals),
                "total_profit": float_2dp(total_profit),
                "total_investors": len(unique_investors),
                "performance_pct": float_2dp(performance_pct),
                "active_batches": int(active_funds),
                "latest_epoch_end": latest_epoch_end.isoformat() if latest_epoch_end else None,
                "max_chart_epoch": max_chart_epoch.isoformat() if max_chart_epoch else None,
                "previous_epoch_end": None,
                "flow_series": flow_series,
                "flow_by_batch": flow_by_batch,
                "alloc_data": alloc_data_list,
                "aum_data": aum_data_obj,
            },
        }), 200

    except Exception as exc:
        pass
        return jsonify({"status": 500, "message": f"Could not fetch overview stats: {str(exc)}"}), 500

