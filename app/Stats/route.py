from collections import defaultdict

from flask import Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import aliased
from decimal import Decimal
from datetime import datetime

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch as BatchModel
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
        # SSOT AUM: aggregate per-investment balances resolved by
        # BatchController._calculate_batch_investment_values (statement-first).
        from app.Batch.controllers import BatchController
        authoritative_total_aum = Decimal("0")
        batch_contributions = {}

        all_batches = db.session.query(BatchModel).all()
        for batch_row in all_batches:
            batch_id = batch_row.id
            batch_balance = Decimal("0")
            batch_profit = Decimal("0")
            latest_period_end = None

            invs = db.session.query(Investment).filter(Investment.batch_id == batch_id).all()
            for inv in invs:
                vals = BatchController._calculate_batch_investment_values(inv, batch_row, db.session)
                batch_balance += Decimal(str(vals.get("current_balance", 0)))
                batch_profit += Decimal(str(vals.get("profit", 0)))

                latest_stmt = BatchController._latest_committed_statement_for_investment_batch(
                    db.session, inv.id, batch_id
                )
                if latest_stmt:
                    _, vr = latest_stmt
                    if latest_period_end is None or vr.epoch_end > latest_period_end:
                        latest_period_end = vr.epoch_end

            batch_balance = Decimal(str(batch_balance.quantize(Decimal("0.01"))))
            authoritative_total_aum += batch_balance
            batch_contributions[batch_id] = {
                "balance": float(batch_balance),
                "profit": float(batch_profit.quantize(Decimal("0.01"))),
                "period_end": latest_period_end.isoformat() if latest_period_end else None,
            }

        # Net principal per batch (fees excluded) and cumulative gain vs latest batch balance
        net_by_batch = defaultdict(Decimal)
        for row in db.session.query(
            Investment.batch_id,
            Investment.amount_deposited,
            Investment.deployment_fee_deducted,
            Investment.transfer_fee_deducted,
        ).all():
            net_by_batch[row.batch_id] += Decimal(str(row.amount_deposited or 0)) - Decimal(
                str(row.deployment_fee_deducted or 0)
            ) - Decimal(str(row.transfer_fee_deducted or 0))

        batch_total_gain = Decimal("0")
        for bid, info in batch_contributions.items():
            bal = Decimal(str(info["balance"]))
            net = net_by_batch.get(bid, Decimal("0"))
            batch_total_gain += bal - net

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

        # ── 2. KPIs: total AUM is batch-authoritative (above). Epoch ledger used for charts only.
        max_chart_epoch = db.session.query(
            func.max(ValuationRun.epoch_end)
        ).filter(
            func.lower(ValuationRun.status) == "committed"
        ).scalar()

        latest_epoch_end = None

        for row in latest_rows:
            if max_chart_epoch and row.epoch_end > max_chart_epoch:
                continue
            if latest_epoch_end is None or row.epoch_end > latest_epoch_end:
                latest_epoch_end = row.epoch_end

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

        # Fund allocation: split each batch's latest AUM by net-principal share within the batch
        fund_totals = defaultdict(Decimal)
        for batch_id, info in batch_contributions.items():
            bal = Decimal(str(info["balance"]))
            batch_net = net_by_batch.get(batch_id, Decimal("0"))
            if batch_net <= 0:
                continue
            inv_rows = (
                db.session.query(Investment, CoreFund.fund_name)
                .outerjoin(CoreFund, Investment.fund_id == CoreFund.id)
                .filter(Investment.batch_id == batch_id)
                .all()
            )
            for inv, core_name in inv_rows:
                np = Decimal(str(inv.amount_deposited or 0)) - Decimal(str(inv.deployment_fee_deducted or 0)) - Decimal(
                    str(inv.transfer_fee_deducted or 0)
                )
                share = np / batch_net
                name = core_name or inv.fund_name or "Unknown"
                fund_totals[name] += bal * share

        alloc_data_list = [
            {"name": name, "value": float_2dp(val)} for name, val in sorted(fund_totals.items(), key=lambda x: x[0])
        ]

        total_invested_net = sum(net_by_batch.values())
        performance_pct = 0.0
        if total_invested_net > 0:
            performance_pct = float(
                ((authoritative_total_aum - total_invested_net) / total_invested_net) * 100
            )

        total_investors = (
            db.session.query(func.count(func.distinct(Investment.internal_client_code))).scalar() or 0
        )

        # ── 3. Flow series — deposits & withdrawals by transaction day ──
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

            active_ct = sum(1 for b in all_batches if getattr(b, "is_active", False))
            return jsonify({
                "status": 200,
                "data": {
                    "total_aum": float_2dp(authoritative_total_aum),
                    "total_profit": float_2dp(batch_total_gain),
                    "total_invested": float_2dp(total_invested_net),
                    "total_investors": int(total_invs),
                    "performance_pct": float_2dp(
                        ((authoritative_total_aum - total_invested_net) / total_invested_net * 100)
                        if total_invested_net > 0
                        else Decimal("0")
                    ),
                    "active_batches": active_ct,
                    "latest_epoch_end": None,
                    "max_chart_epoch": None,
                    "previous_epoch_end": None,
                    "flow_series": flow_series,
                    "flow_by_batch": flow_by_batch,
                    "alloc_data": alloc_data_list,
                    "aum_data": {"labels": ["—"], "funds": []},
                    "batch_contributions": batch_contributions,
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

        active_batches_count = sum(1 for b in all_batches if getattr(b, "is_active", False))
        prev_epoch = (
            db.session.query(ValuationRun.epoch_end)
            .filter(func.lower(ValuationRun.status) == "committed")
            .order_by(ValuationRun.epoch_end.desc())
            .offset(1)
            .limit(1)
            .scalar()
        )

        return make_response(
            jsonify(
                {
                    "status": 200,
                    "message": "Overview stats retrieved successfully",
                    "data": {
                        "total_aum": float_2dp(authoritative_total_aum),
                        "total_profit": float_2dp(batch_total_gain),
                        "total_invested": float_2dp(total_invested_net),
                        "total_investors": int(total_investors),
                        "performance_pct": float_2dp(performance_pct),
                        "active_batches": active_batches_count,
                        "latest_epoch_end": latest_epoch_end.isoformat() if latest_epoch_end else None,
                        "max_chart_epoch": max_chart_epoch.isoformat() if max_chart_epoch else None,
                        "previous_epoch_end": prev_epoch.isoformat() if prev_epoch else None,
                        "flow_series": flow_series,
                        "flow_by_batch": flow_by_batch,
                        "alloc_data": alloc_data_list,
                        "aum_data": aum_data_obj,
                        "batch_contributions": batch_contributions,
                    },
                }
            ),
            200,
        )

    except Exception as exc:
        return jsonify({"status": 500, "message": f"Could not fetch overview stats: {str(exc)}"}), 500

