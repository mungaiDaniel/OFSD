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
from app.Investments.model import EpochLedger, Withdrawal, Investment, FINAL_WITHDRAWAL_STATUSES, WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND

stats_v1 = Blueprint("stats_v1", __name__, url_prefix="/")


def float_2dp(val) -> float:
    if val is None:
        return 0.0
    return float(Decimal(str(val)).quantize(Decimal("0.01")))


@stats_v1.route("/api/v1/stats/overview", methods=["GET"])
@jwt_required()
def get_overview_stats():
    try:
        from app.Batch.controllers import BatchController

        # Authoritative batch AUM:
        # Read each batch's current standing from the write-time cache
        # (batch.cached_total_capital — kept fresh on deploy/withdrawal-approval/
        # valuation-commit; see BatchController.refresh_cached_total_capital)
        # instead of recomputing the full per-investment valuation cascade for
        # every batch on every Overview load. Falls back to a live recompute
        # (and self-heals the cache) only for batches that predate the cache.
        all_batches = db.session.query(BatchModel).all()

        authoritative_total_aum = Decimal("0")
        total_aum_kes = Decimal("0")
        total_aum_usd = Decimal("0")
        batch_contributions: dict[int, dict[str, object]] = {}
        batch_currency: dict[int, str] = {}
        for batch in all_batches:
            if batch.cached_total_capital is not None:
                balance = float(batch.cached_total_capital)
            else:
                balance = BatchController.refresh_cached_total_capital(batch, db.session)
            balance_dec = Decimal(str(balance or 0))
            authoritative_total_aum += balance_dec
            batch_contributions[batch.id] = {
                "balance": float(balance_dec),
                "profit": 0.0,
                "period_end": None,
            }
            currency = ((batch.share_class.currency if getattr(batch, "share_class", None) else None) or "")
            currency = currency.strip().upper()
            # SHARES (DPRP) balances are NGN whatever the class's deposit
            # currency is — they're reported on the separate NGN figures below,
            # never in these KES/USD buckets.
            if getattr(batch, "product_type", None) == "SHARES":
                currency = "NGN"
            if currency == "KES":
                total_aum_kes += balance_dec
            elif currency == "USD":
                total_aum_usd += balance_dec
            batch_currency[batch.id] = currency or ""

        # Net principal per batch (fees excluded) and cumulative gain vs latest batch
        # balance — computed as a single SQL aggregate (one row per batch) instead of
        # loading every investment row into Python to sum them.
        net_by_batch = defaultdict(Decimal)
        net_by_batch_rows = db.session.query(
            Investment.batch_id,
            func.coalesce(
                func.sum(
                    Investment.amount_deposited
                    - func.coalesce(Investment.deployment_fee_deducted, 0)
                    - func.coalesce(Investment.transfer_fee_deducted, 0)
                ),
                0,
            ).label("net"),
        ).group_by(Investment.batch_id).all()
        for batch_id, net in net_by_batch_rows:
            net_by_batch[batch_id] = Decimal(str(net or 0))

        batch_total_gain = Decimal("0")
        invested_kes = Decimal("0")
        invested_usd = Decimal("0")
        gain_kes = Decimal("0")
        gain_usd = Decimal("0")
        for bid, info in batch_contributions.items():
            bal = Decimal(str(info["balance"]))
            net = net_by_batch.get(bid, Decimal("0"))
            gain = bal - net
            batch_total_gain += gain
            info["profit"] = float(gain)

            currency = batch_currency.get(bid, "")
            if currency == "KES":
                invested_kes += net
                gain_kes += gain
            elif currency == "USD":
                invested_usd += net
                gain_usd += gain

        # ── Synchronize with Funds Summary (landing page authoritative data) ──
        from app.Funds.routes import compute_funds_summary_data
        from app.Investments.route import get_total_investors_count

        funds_summary = compute_funds_summary_data(db.session)
        funds_list = funds_summary.get("funds", [])

        summary_aum_kes = Decimal("0")
        summary_aum_usd = Decimal("0")
        summary_inv_kes = Decimal("0")
        summary_inv_usd = Decimal("0")
        summary_gain_kes = Decimal("0")
        summary_gain_usd = Decimal("0")
        summary_shares_usd = Decimal("0")
        summary_shares_kes = Decimal("0")

        for f_item in funds_list:
            t_map = f_item.get("totals_by_currency") or {}
            i_map = f_item.get("invested_by_currency") or {}
            g_map = f_item.get("gain_by_currency") or {}

            if "KES" in t_map:
                summary_aum_kes += Decimal(str(t_map["KES"] or 0))
            if "USD" in t_map:
                summary_aum_usd += Decimal(str(t_map["USD"] or 0))

            if "KES" in i_map:
                summary_inv_kes += Decimal(str(i_map["KES"] or 0))
            if "USD" in i_map:
                summary_inv_usd += Decimal(str(i_map["USD"] or 0))

            if "KES" in g_map:
                summary_gain_kes += Decimal(str(g_map["KES"] or 0))
            if "USD" in g_map:
                summary_gain_usd += Decimal(str(g_map["USD"] or 0))

            for cls_item in f_item.get("classes", []):
                sh = Decimal(str(cls_item.get("total_shares") or 0))
                if cls_item.get("currency") == "USD":
                    summary_shares_usd += sh
                elif cls_item.get("currency") == "KES":
                    summary_shares_kes += sh

        if summary_aum_kes > 0 or summary_aum_usd > 0:
            total_aum_kes = summary_aum_kes
            total_aum_usd = summary_aum_usd
            invested_kes = summary_inv_kes
            invested_usd = summary_inv_usd
            gain_kes = summary_gain_kes
            gain_usd = summary_gain_usd
            authoritative_total_aum = summary_aum_usd
            batch_total_gain = summary_gain_usd

        # ── Task 10: Shares (SHARES/DPRP) NGN total — same synchronize-with-
        # Funds-Summary approach as KES/USD above, just scoped to the SHARES
        # product instead of FUNDS, so Overview's NGN card/chart never mixes
        # Funds and Shares figures (see Task 9's product_type separation).
        from app.database.product_type import SHARES as SHARES_PRODUCT

        shares_summary = compute_funds_summary_data(db.session, product=SHARES_PRODUCT)
        total_ngn = Decimal("0")
        invested_ngn = Decimal("0")
        gain_ngn = Decimal("0")
        for f_item in shares_summary.get("funds", []):
            t_map = f_item.get("totals_by_currency") or {}
            i_map = f_item.get("invested_by_currency") or {}
            g_map = f_item.get("gain_by_currency") or {}
            if "NGN" in t_map:
                total_ngn += Decimal(str(t_map["NGN"] or 0))
            if "NGN" in i_map:
                invested_ngn += Decimal(str(i_map["NGN"] or 0))
            if "NGN" in g_map:
                gain_ngn += Decimal(str(g_map["NGN"] or 0))

        # Authoritative investor count matching the investor directory page
        total_investors_count = get_total_investors_count(db.session)
        if total_investors_count == 0:
            total_investors_count = (
                db.session.query(func.count(func.distinct(Investment.internal_client_code))).scalar() or 0
            )

        # Authoritative batch counts matching the batches directory page
        batch_counts = BatchController.get_batches_summary_counts(db.session)

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

        # Fund allocation: split each batch's latest AUM by net-principal share within the
        # batch. Net principal per (batch, fund) is computed as a single grouped SQL
        # aggregate — this used to re-fetch every investment row once per batch.
        fund_net_rows = (
            db.session.query(
                Investment.batch_id,
                func.coalesce(CoreFund.fund_name, Investment.fund_name, "Unknown").label("fund_name"),
                func.coalesce(
                    func.sum(
                        Investment.amount_deposited
                        - func.coalesce(Investment.deployment_fee_deducted, 0)
                        - func.coalesce(Investment.transfer_fee_deducted, 0)
                    ),
                    0,
                ).label("net"),
            )
            .outerjoin(CoreFund, Investment.fund_id == CoreFund.id)
            .group_by(Investment.batch_id, func.coalesce(CoreFund.fund_name, Investment.fund_name, "Unknown"))
            .all()
        )

        fund_totals = defaultdict(Decimal)
        for batch_id, fund_name, net in fund_net_rows:
            np = Decimal(str(net or 0))
            batch_net = net_by_batch.get(batch_id, Decimal("0"))
            if batch_net <= 0:
                continue
            bal = Decimal(str(batch_contributions.get(batch_id, {}).get("balance", 0)))
            share = np / batch_net
            fund_totals[fund_name] += bal * share

        if funds_list and (summary_aum_kes > 0 or summary_aum_usd > 0):
            alloc_data_list = [
                {
                    "name": f_item.get("fund_name") or "Fund",
                    "value": float_2dp(sum(Decimal(str(v or 0)) for v in (f_item.get("totals_by_currency") or {}).values())),
                }
                for f_item in funds_list
            ]
            total_invested_net = summary_inv_usd
            if invested_usd > 0:
                performance_pct = float(((total_aum_usd - invested_usd) / invested_usd) * 100)
            else:
                performance_pct = 0.0
            if summary_shares_usd > 0:
                total_shares_usd = summary_shares_usd
            if summary_shares_kes > 0:
                total_shares_kes = summary_shares_kes
        else:
            total_invested_net = sum(net_by_batch.values())
            performance_pct = 0.0
            if total_invested_net > 0:
                performance_pct = float(
                    ((authoritative_total_aum - total_invested_net) / total_invested_net) * 100
                )
            # Build alloc_data from fund_totals (batch-split proportional allocation)
            alloc_data_list = [
                {"name": name, "value": float_2dp(val)}
                for name, val in sorted(fund_totals.items())
                if val > 0
            ] or [{"name": "No data", "value": 0.0}]

        total_investors = total_investors_count
        total_shares_usd = Decimal(
            str(
                db.session.query(func.coalesce(func.sum(Investment.shares_owned), 0))
                .filter(Investment.currency_type == "USD")
                .scalar()
                or 0
            )
        )
        total_shares_kes = Decimal(
            str(
                db.session.query(func.coalesce(func.sum(Investment.shares_owned), 0))
                .filter(Investment.currency_type == "KES")
                .scalar()
                or 0
            )
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
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
            Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
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
            ).filter(
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            ).scalar() or 0
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
                    # Currency splits are based on batch share-class currency.
                    "total_aum_kes": float_2dp(total_aum_kes),
                    "total_aum_usd": float_2dp(total_aum_usd),
                    "invested_kes": float_2dp(invested_kes),
                    "invested_usd": float_2dp(invested_usd),
                    "gain_kes": float_2dp(gain_kes),
                    "gain_usd": float_2dp(gain_usd),
                    "total_ngn": float_2dp(total_ngn),
                    "invested_ngn": float_2dp(invested_ngn),
                    "gain_ngn": float_2dp(gain_ngn),
                    "total_investors": int(total_investors_count),
                    "active_investors": int(total_investors_count),
                    "performance_pct": float_2dp(
                        ((authoritative_total_aum - total_invested_net) / total_invested_net * 100)
                        if total_invested_net > 0
                        else Decimal("0")
                    ),
                    "active_batches": batch_counts["active_batches"],
                    "open_batches": batch_counts["open_batches"],
                    "total_batches": batch_counts["total_batches"],
                    "latest_epoch_end": None,
                    "max_chart_epoch": None,
                    "previous_epoch_end": None,
                    "flow_series": flow_series,
                    "flow_by_batch": flow_by_batch,
                    "alloc_data": alloc_data_list,
                    "aum_data": {"labels": ["—"], "funds": []},
                    "batch_contributions": batch_contributions,
                    "total_shares_usd": float(total_shares_usd.quantize(Decimal("0.0001"))),
                    "total_shares_kes": float(total_shares_kes.quantize(Decimal("0.0001"))),
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
                        "total_aum_kes": float_2dp(total_aum_kes),
                        "total_aum_usd": float_2dp(total_aum_usd),
                        "invested_kes": float_2dp(invested_kes),
                        "invested_usd": float_2dp(invested_usd),
                        "gain_kes": float_2dp(gain_kes),
                        "gain_usd": float_2dp(gain_usd),
                        "total_ngn": float_2dp(total_ngn),
                        "invested_ngn": float_2dp(invested_ngn),
                        "gain_ngn": float_2dp(gain_ngn),
                        "total_investors": int(total_investors),
                        "active_investors": int(total_investors),
                        "performance_pct": float_2dp(performance_pct),
                        "active_batches": batch_counts["active_batches"],
                        "open_batches": batch_counts["open_batches"],
                        "total_batches": batch_counts["total_batches"],
                        "latest_epoch_end": latest_epoch_end.isoformat() if latest_epoch_end else None,
                        "max_chart_epoch": max_chart_epoch.isoformat() if max_chart_epoch else None,
                        "previous_epoch_end": prev_epoch.isoformat() if prev_epoch else None,
                        "flow_series": flow_series,
                        "flow_by_batch": flow_by_batch,
                        "alloc_data": alloc_data_list,
                        "aum_data": aum_data_obj,
                        "batch_contributions": batch_contributions,
                        "total_shares_usd": float(total_shares_usd.quantize(Decimal("0.0001"))),
                        "total_shares_kes": float(total_shares_kes.quantize(Decimal("0.0001"))),
                    },
                }
            ),
            200,
        )

    except Exception as exc:
        return jsonify({"status": 500, "message": f"Could not fetch overview stats: {str(exc)}"}), 500

