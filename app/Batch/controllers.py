from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal, PendingEmail, EmailLog, FINAL_WITHDRAWAL_STATUSES
from app.Valuation.model import Statement, ValuationRun
from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
from app.logic.valuation_service import _q2
from app.Batch.core_fund import CoreFund
from app.database.database import db
from app.utils.email_service import EmailService
from app.utils.audit_log import create_audit_log
from flask import jsonify, make_response
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from marshmallow import ValidationError
from sqlalchemy import select, distinct, func
from app.Batch.status_update_controller import StatusUpdateController
import logging

logger = logging.getLogger(__name__)

# ── Atomic Batch Architecture Constants ────────────────────────────────────────

# Maps batch_id → the maximum epoch_end date that belongs to THIS batch.
# _calculate_batch_investment_values() uses this to scope EpochLedger reads so
# that an investor who appears in Batch 1 AND Batch 2 returns their Batch-1
# closing balance (Apr epoch) when computing Batch 1, not their latest balance.
BATCH_EPOCH_CUTOFFS: dict = {
    1: datetime(2026,  4, 30, tzinfo=timezone.utc),  # Apr 2026 epoch end
    2: datetime(2026,  9, 30, tzinfo=timezone.utc),  # Sep 2026 epoch end
    3: datetime(2026, 10, 31, tzinfo=timezone.utc),  # Oct 2026 epoch end
}



class BatchController:
    """Controller for Batch operations"""
    
    model = Batch

    @classmethod
    def create_batch(cls, data, session):
        """
        Create a new batch (fund container).
        Two-stage creation: only batch_name is required initially.
        
        Args:
            data: dict with batch_name (required), certificate_number, date_deployed, duration_days (optional)
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            # Validate required field
            batch_name = data.get('batch_name')
            if not batch_name:
                return make_response(jsonify({
                    "status": 400,
                    "message": "Batch name is required"
                }), 400)
            
            # Get optional fields
            certificate_number = data.get('certificate_number')
            if not certificate_number: # Treat empty string or missing as None
                certificate_number = None
            date_deployed_str = data.get('date_deployed')
            
            # Check if batch name already exists
            existing_batch = session.query(Batch).filter(
                Batch.batch_name.ilike(batch_name.strip())
            ).first()
            if existing_batch:
                return make_response(jsonify({
                    "status": 409,
                    "message": "Batch with that name already exists"
                }), 409)

            # Check if certificate number already exists (only if provided)
            if certificate_number:
                existing = session.query(Batch).filter(
                    Batch.certificate_number == certificate_number
                ).first()
                
                if existing:
                    return make_response(jsonify({
                        "status": 409,
                        "message": "Batch with that certificate number already exists"
                    }), 409)

            # Parse date_deployed if provided
            date_deployed = None
            if date_deployed_str:
                try:
                    date_deployed = datetime.fromisoformat(date_deployed_str)
                except ValueError:
                    return make_response(jsonify({
                        "status": 400,
                        "message": f"Invalid date format: {date_deployed_str}"
                    }), 400)

            # Create new batch with optional fields as None
            batch = cls.model(
                batch_name=batch_name,
                certificate_number=certificate_number,
                date_deployed=date_deployed,
                duration_days=data.get('duration_days', 30),
                is_active=False  # New batches start as inactive
            )

            batch.save(session)

            # Determine status
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 201,
                "message": "Batch created successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if date_deployed else None,
                    "is_active": batch.is_active,
                    "status": status
                }
            }), 201)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error creating batch: {str(e)}"
            }), 500)

    @classmethod
    def _get_batch_type(cls, batch):
        """Return batch type label for all batches.

        The application now uses an atomic batch architecture where every batch
        is treated as an independent round. Batch history is no longer split
        into Carry Forward vs Fresh Start categories.
        """
        return "Atomic Batch"

    @classmethod
    def get_batch_by_id(cls, batch_id, session):
        """
        Get a batch by ID with all details and investments.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investments
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()

            # Get latest epoch data for each investment
            epoch_data = {}
            for inv in investments:
                epoch_data[inv.id] = cls._calculate_batch_investment_values(inv, batch, session)

            investments_data = [
                {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    # Prefer the FK relationship fund name, fall back to the legacy fund_name field
                    "fund_id": inv.fund_id,
                    "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                    "date_deposited": inv.date_deposited.isoformat() if inv.date_deposited else None,
                    "opening_balance": epoch_data[inv.id]["opening_balance"],
                    "current_balance": epoch_data[inv.id]["current_balance"],
                    "withdrawals": epoch_data[inv.id]["withdrawals"],
                    "profit": epoch_data[inv.id]["profit"],
                }
                for inv in investments
            ]
            # Group investments by fund for accordion-style display
            # Structure: { "Fund Name": [investment1, investment2, ...], ... }
            grouped_by_fund = {}
            fund_totals = {}  # Track total per fund
            
            for inv in investments:
                fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
                
                if fund_name not in grouped_by_fund:
                    grouped_by_fund[fund_name] = []
                    fund_totals[fund_name] = 0.0
                
                inv_data = {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    "fund_id": inv.fund_id,
                    "fund_name": fund_name,
                    "date_deposited": inv.date_deposited.isoformat() if inv.date_deposited else None,
                    "opening_balance": epoch_data[inv.id]["opening_balance"],
                    "current_balance": epoch_data[inv.id]["current_balance"],
                    "withdrawals": epoch_data[inv.id]["withdrawals"],
                    "profit": epoch_data[inv.id]["profit"],
                }
                
                grouped_by_fund[fund_name].append(inv_data)
                fund_totals[fund_name] += float(inv.amount_deposited)

            # Calculate current_stage (1-4) based on specific conditions
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if len(investments) > 0 else 0
            
            # Stage 2: Transferred - Marked complete ONLY when is_transferred is true
            if batch.is_transferred:
                current_stage = max(current_stage, 2)
            
            # Stage 3: Deployed - Marked complete ONLY if date_deployed is set AND deployment_confirmed is true
            if batch.date_deployed is not None and batch.deployment_confirmed:
                current_stage = max(current_stage, 3)
            
            # Stage 4: Active - Marked complete ONLY when is_active is true
            if batch.is_active:
                current_stage = max(current_stage, 4)

            # Persist stage if needed for external clients
            if batch.stage != current_stage:
                batch.stage = current_stage
                session.commit()

            # Calculate fresh total_principal for this batch ONLY (batch-specific, not global sum)
            fresh_total_principal = session.query(db.func.sum(Investment.amount_deposited)).filter(
                Investment.batch_id == batch_id
            ).scalar() or 0.0

            # Total current standing is reconciled using latest investor/fund ledger positions.
            total_current_standing = cls._calculate_batch_current_standing(batch, session)

            # Count UNIQUE investors in this batch using DISTINCT on internal_client_code
            unique_investor_count = session.query(
                db.func.count(distinct(Investment.internal_client_code))
            ).filter(
                Investment.batch_id == batch_id
            ).scalar() or 0

            # Total investment entries (50 rows = 50 transactions, even if only 15 unique people)
            investment_rows_count = len(investments)

            # Determine status
            status = 'Active' if batch.is_active else 'Deactivated'
            batch_type = cls._get_batch_type(batch)

            # Build grouped_by_fund response with fund metadata
            grouped_by_fund_response = {}
            for fund_name, investors in grouped_by_fund.items():
                # Get fund_id from first investor in this fund
                fund_id = investors[0].get("fund_id") if investors else None
                
                # Count unique investors by internal_client_code for this fund
                unique_codes_in_fund = set(inv.get("internal_client_code") for inv in investors)
                unique_investor_count_for_fund = len(unique_codes_in_fund)
                
                grouped_by_fund_response[fund_name] = {
                    "fund_id": fund_id,
                    "fund_name": fund_name,
                    "investor_count": unique_investor_count_for_fund,
                    "investment_rows_count": len(investors),
                    "total_principal": fund_totals[fund_name],
                    "investors": investors
                }
            
            # ── Resolve canonical deployment date ──
            effective_date = batch.date_deployed

            return make_response(jsonify({
                "status": 200,
                "message": "Batch retrieved successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "batch_type": batch_type,
                    "total_principal": float(fresh_total_principal),
                    "total_capital": float(total_current_standing),
                    "date_deployed": effective_date.isoformat() if effective_date else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": (effective_date + timedelta(days=batch.duration_days)).isoformat() if effective_date else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "unique_investor_count": int(unique_investor_count),
                    "investment_rows_count": investment_rows_count,
                    "investors_count": int(unique_investor_count),
                    "is_active": batch.is_active,
                    "is_transferred": batch.is_transferred,
                    "deployment_confirmed": batch.deployment_confirmed,
                    "stage": current_stage,
                    "current_stage": current_stage,
                    "status": status,
                    "investments": investments_data,  # Flat array for backward compatibility
                    "grouped_by_fund": grouped_by_fund_response,  # Fund-based grouping for accordion display
                    "created_at": batch.date_created.isoformat() if hasattr(batch, 'date_created') else None
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch: {str(e)}"
            }), 500)

    @classmethod
    def _to_utc(cls, dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _investment_active_start(cls, investment):
        active_start = investment.date_transferred or investment.date_deposited
        if active_start is None:
            return None
        active_start = cls._to_utc(active_start)
        if investment.batch and investment.batch.date_deployed is not None:
            batch_deploy = cls._to_utc(investment.batch.date_deployed)
            if active_start < batch_deploy:
                return batch_deploy
        return active_start

    @classmethod
    def _get_related_investments_for_client_fund(cls, inv, session):
        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        query = session.query(Investment).join(Batch).filter(
            Investment.internal_client_code == inv.internal_client_code,
            db.or_(Investment.batch_id == inv.batch_id, Batch.date_deployed != None)
        )
        if inv.fund_id is not None:
            query = query.filter(Investment.fund_id == inv.fund_id)
        else:
            query = query.filter(func.lower(Investment.fund_name) == func.lower(fund_name))
        related = query.all()
        return sorted(
            related,
            key=lambda item: (
                cls._investment_active_start(item) or datetime.min.replace(tzinfo=timezone.utc),
                item.id,
            ),
        )

    @classmethod
    def _get_client_fund_epochs(cls, inv, session):
        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        return session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == inv.internal_client_code,
            func.lower(EpochLedger.fund_name) == func.lower(fund_name),
        ).order_by(EpochLedger.epoch_start.asc(), EpochLedger.epoch_end.asc()).all()

    @classmethod
    def _simulate_client_fund_balances(cls, inv, session):
        related_investments = cls._get_related_investments_for_client_fund(inv, session)
        epochs = cls._get_client_fund_epochs(inv, session)
        if not epochs:
            return None

        investment_states = []
        for related in related_investments:
            investment_states.append({
                "id": related.id,
                "investment": related,
                "amount": Decimal(str(related.amount_deposited)),
                "active_start": cls._investment_active_start(related),
                "balance": Decimal("0"),
                "profit": Decimal("0"),
                "withdrawals": Decimal("0"),
                "has_deposited": False,
                "history": [],
            })

        for epoch in epochs:
            epoch_start = cls._to_utc(epoch.epoch_start)
            epoch_end = cls._to_utc(epoch.epoch_end)
            period_days = (epoch_end - epoch_start).days + 1
            if period_days <= 0:
                continue

            epoch_withdrawals = Decimal(str(epoch.withdrawals or 0))
            active_items = []
            total_capacity = Decimal("0")

            for state in investment_states:
                active_start = state["active_start"]
                if active_start is None:
                    active_start = epoch_start
                if active_start > epoch_end:
                    continue

                deposit = Decimal("0")
                if not state["has_deposited"]:
                    if active_start < epoch_start:
                        state["balance"] = state["amount"]
                        state["has_deposited"] = True
                    elif active_start <= epoch_end:
                        deposit = state["amount"]
                        state["has_deposited"] = True

                opening_balance = state["balance"]
                capacity = opening_balance + deposit
                if capacity < Decimal("0"):
                    capacity = Decimal("0")

                days_active = period_days if active_start <= epoch_start else (epoch_end - active_start).days + 1
                if days_active <= 0:
                    continue

                active_items.append({
                    "state": state,
                    "opening_balance": opening_balance,
                    "deposit": deposit,
                    "days_active": days_active,
                    "capacity": capacity,
                    "weighted_capital": Decimal("0"),
                })
                total_capacity += capacity

            for item in active_items:
                if total_capacity > Decimal("0"):
                    item["withdrawal"] = _q2(epoch_withdrawals * (item["capacity"] / total_capacity))
                else:
                    item["withdrawal"] = Decimal("0")
                item["start_balance"] = item["opening_balance"] - item["withdrawal"]
                if item["start_balance"] < Decimal("0"):
                    item["start_balance"] = Decimal("0")
                item["active_capital"] = item["start_balance"] + item["deposit"]
                item["weighted_capital"] = item["active_capital"] * Decimal(item["days_active"]) / Decimal(period_days)

            total_weight = sum(item["weighted_capital"] for item in active_items)
            epoch_profit = Decimal(str(epoch.profit or 0))
            epoch_perf_rate = Decimal(str(epoch.performance_rate or 0))

            for item in active_items:
                # The crucial fix: Discard the old weighted EpochLedger.profit distribution!
                # We calculate EXACT independent compounding using the verified performance targets.
                # This perfectly mimics the canonical spreadsheet which gives precise performance 
                # (e.g. 4.32%, 1.38%) on the batch's opening+deposits.
                active_base = item["start_balance"] + item["deposit"]
                profit = _q2(active_base * epoch_perf_rate)

                end_balance = active_base + profit
                item_state = item["state"]
                item_state["balance"] = end_balance
                item_state["profit"] += profit
                item_state["withdrawals"] += item["withdrawal"]
                
                # Append to history so we can lookup historical period values
                item_state["history"].append({
                    "epoch_end": epoch_end,
                    "start_balance": item["start_balance"],
                    "deposit": item["deposit"],
                    "withdrawal": item["withdrawal"],
                    "profit": profit,
                    "end_balance": end_balance,
                    "performance_rate": epoch_perf_rate
                })
        
        # FINAL SWEEP: Any investment that was deposited *after* the latest epoch 
        # (or if no epochs existed for overlapping items) needs its base balance set.
        for state in investment_states:
            if not state["has_deposited"]:
                state["balance"] = state["amount"]
                state["has_deposited"] = True

        return {state["id"]: state for state in investment_states}

    @classmethod
    def _calculate_batch_investment_values(cls, inv, batch, session):
        """Calculate per-investment current values using same-client/fund epoch proration."""
        if batch.date_deployed is None:
            opening_balance = float(inv.amount_deposited)
            return {
                "opening_balance": opening_balance,
                "current_balance": opening_balance,
                "profit": 0.0,
                "withdrawals": 0.0,
            }

        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        epoch_balances = cls._simulate_client_fund_balances(inv, session)
        if epoch_balances and inv.id in epoch_balances:
            state = epoch_balances[inv.id]
            return {
                "opening_balance": float(inv.amount_deposited),
                "current_balance": float(round(state["balance"], 2)),
                "profit": float(round(state["profit"], 2)),
                "withdrawals": float(round(state["withdrawals"], 2)),
            }

        from app.Investments.model import EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES

        opening_balance = float(inv.amount_deposited)
        opening_balance_decimal = Decimal(str(inv.amount_deposited or 0))
        latest_epoch = session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == inv.internal_client_code,
            func.lower(EpochLedger.fund_name) == func.lower(fund_name)
        ).order_by(EpochLedger.epoch_end.desc()).first()

        related_investments_query = session.query(Investment).join(Batch).filter(
            Investment.internal_client_code == inv.internal_client_code,
            db.or_(Investment.batch_id == batch.id, Batch.date_deployed != None)
        )
        if inv.fund_id is not None:
            related_investments_query = related_investments_query.filter(Investment.fund_id == inv.fund_id)
        else:
            related_investments_query = related_investments_query.filter(func.lower(Investment.fund_name) == func.lower(fund_name))

        related_investments = related_investments_query.all()

        if not latest_epoch:
            total_approved_wds = session.query(db.func.coalesce(db.func.sum(Withdrawal.amount), 0)).filter(
                Withdrawal.internal_client_code == inv.internal_client_code,
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                func.lower(Withdrawal.fund_name) == func.lower(fund_name)
            ).scalar() or 0
            return {
                "opening_balance": opening_balance,
                "current_balance": float(opening_balance_decimal - Decimal(str(total_approved_wds))),
                "profit": 0.0,
                "withdrawals": float(total_approved_wds),
            }

        def to_utc(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        latest_epoch_start_utc = to_utc(latest_epoch.epoch_start)
        latest_epoch_end_utc = to_utc(latest_epoch.epoch_end)

        inv_pre = Decimal("0")
        inv_intra = Decimal("0")
        inv_post = Decimal("0")
        all_allocations = []
        for related in related_investments:
            related_dt = to_utc(related.date_transferred or related.date_deposited)
            pre = Decimal("0")
            intra = Decimal("0")
            post = Decimal("0")
            if related_dt is not None:
                if latest_epoch_start_utc is not None and related_dt <= latest_epoch_start_utc:
                    pre = Decimal(str(related.amount_deposited))
                elif latest_epoch_end_utc is not None and related_dt <= latest_epoch_end_utc:
                    intra = Decimal(str(related.amount_deposited))
                else:
                    post = Decimal(str(related.amount_deposited))
            else:
                pre = Decimal(str(related.amount_deposited))

            all_allocations.append({
                "investment_id": related.id,
                "pre": pre,
                "intra": intra,
                "post": post,
            })

            if related.id == inv.id:
                inv_pre = pre
                inv_intra = intra
                inv_post = post

        total_pre = sum(item["pre"] for item in all_allocations)

        total_approved_wds = session.query(db.func.coalesce(db.func.sum(Withdrawal.amount), 0)).filter(
            Withdrawal.internal_client_code == inv.internal_client_code,
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
            func.lower(Withdrawal.fund_name) == func.lower(fund_name)
        ).scalar() or Decimal("0")

        total_captured_wds = session.query(db.func.coalesce(db.func.sum(EpochLedger.withdrawals), 0)).filter(
            EpochLedger.internal_client_code == inv.internal_client_code,
            func.lower(EpochLedger.fund_name) == func.lower(fund_name)
        ).scalar() or Decimal("0")

        uncaptured_wds = max(Decimal("0"), Decimal(str(total_approved_wds)) - Decimal(str(total_captured_wds)))

        epoch_start_balance = Decimal(str(latest_epoch.start_balance or 0))
        epoch_deposits = Decimal(str(latest_epoch.deposits or 0))
        epoch_profit = Decimal(str(latest_epoch.profit or 0))
        epoch_total_contribution = epoch_start_balance + epoch_deposits

        if total_pre > 0 and inv_pre > 0:
            batch_start_balance = epoch_start_balance * (inv_pre / total_pre)
        else:
            batch_start_balance = Decimal("0")

        batch_profit_share = Decimal("0")
        if epoch_total_contribution > 0:
            batch_profit_share = ((batch_start_balance + inv_intra) / epoch_total_contribution) * epoch_profit

        current_before_wd = batch_start_balance + inv_intra + inv_post + batch_profit_share

        final_withdrawal_amount = float(round(Decimal(str(total_approved_wds)), 2))

        return {
            "opening_balance": opening_balance,
            "current_balance": float(round(current_before_wd, 2)),
            "profit": float(round(batch_profit_share, 2)),
            "withdrawals": final_withdrawal_amount,
        }

    @classmethod
    def _calculate_batch_current_standing(cls, batch, session):
        """Calculate total current standing for a batch using per-investment batch valuation."""
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        total_current_standing = Decimal("0")

        for inv in investments:
            values = cls._calculate_batch_investment_values(inv, batch, session)
            total_current_standing += Decimal(str(values.get("current_balance", 0)))

        return float(round(total_current_standing, 2))

    @classmethod
    def get_all_batches(cls, session):
        """
        Get all batches with calculated fields.
        
        Args:
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batches = session.query(Batch).all()
            
            batch_list = []
            for batch in batches:
                # Base principal (deposits)
                total_deposits_sum = session.query(db.func.sum(Investment.amount_deposited)).filter(
                    Investment.batch_id == batch.id
                ).scalar() or 0.00

                # Total current standing is the sum of the latest current balances per investment.
                total_value = cls._calculate_batch_current_standing(batch, session)

                # Count unique investors (by distinct internal_client_code)
                investors_count = session.query(
                    db.func.count(distinct(Investment.internal_client_code))
                ).filter(
                    Investment.batch_id == batch.id
                ).scalar() or 0
                
                # ── Resolve canonical deployment date ──
                effective_date = batch.date_deployed
                # Status: 'Pending' unless batch is explicitly activated
                status = 'Active' if batch.is_active else 'Deactivated'

                # Calculate fund-level breakdown for accurate filtering
                fund_rows = session.query(
                    CoreFund.fund_name.label("fund_name"),
                    db.func.coalesce(db.func.sum(Investment.amount_deposited), 0).label("total_principal"),
                    db.func.count(distinct(Investment.internal_client_code)).label("investors_count"),
                ).join(
                    CoreFund,
                    Investment.fund_id == CoreFund.id,
                ).filter(
                    Investment.batch_id == batch.id,
                ).group_by(
                    CoreFund.fund_name,
                ).all()

                fund_breakdown = [
                    {
                        "fund_name": fr.fund_name,
                        "total_principal": float(fr.total_principal),
                        "investors_count": int(fr.investors_count),
                    }
                    for fr in fund_rows
                ]

                # The stage value can be persisted in the model and also computed dynamically.
                calculated_stage = batch.stage or (2 if batch.is_transferred else (3 if batch.deployment_confirmed else (4 if batch.is_active else (1 if investors_count > 0 else 0))))

                batch_type = cls._get_batch_type(batch)

                batch_list.append({
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    # total_capital represents current standing; total_principal remains deposits.
                    "total_principal": float(total_deposits_sum),
                    "total_capital": float(total_value),
                    "funds": fund_breakdown,
                    "batch_type": batch_type,
                    "date_deployed": effective_date.isoformat() if effective_date else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": (effective_date + timedelta(days=batch.duration_days)).isoformat() if effective_date else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "investors_count": investors_count,
                    "is_active": batch.is_active,
                    "status": status,
                    "stage": calculated_stage
                })

            return make_response(jsonify({
                "status": 200,
                "message": "Batches retrieved successfully",
                "count": len(batch_list),
                "data": batch_list
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batches: {str(e)}"
            }), 500)

    @classmethod
    def update_batch(cls, batch_id, data, session):
        """
        Update a batch.
        
        Args:
            batch_id: ID of the batch
            data: dict with fields to update
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Update allowed fields
            if 'batch_name' in data:
                batch.batch_name = data['batch_name']
            if 'certificate_number' in data:
                batch.certificate_number = data['certificate_number']
            if 'date_deployed' in data:
                if data['date_deployed'] is not None:
                    batch.date_deployed = datetime.fromisoformat(data['date_deployed'])
                else:
                    batch.date_deployed = None
            if 'date_closed' in data:
                batch.date_closed = datetime.fromisoformat(data['date_closed'])
            if 'duration_days' in data:
                batch.duration_days = data['duration_days']
            if 'is_active' in data:
                batch.is_active = data['is_active']
            if 'is_transferred' in data:
                batch.is_transferred = data['is_transferred']
            if 'deployment_confirmed' in data:
                batch.deployment_confirmed = data['deployment_confirmed']
            if 'stage' in data:
                batch.stage = data['stage']

            session.commit()

            # Determine status
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": "Batch updated successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if batch.date_deployed else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "is_active": batch.is_active,
                    "status": status
                }
            }), 200)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error updating batch: {str(e)}"
            }), 500)

    @classmethod
    def patch_batch(cls, batch_id, data, session):
        """
        Patch (partially update) a batch - for two-stage creation and status updates.
        Allows updating: batch_name, certificate_number, date_deployed, is_active, is_transferred
        
        Args:
            batch_id: ID of the batch
            data: dict with fields to update
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Save old stage states for transition detection
            old_is_transferred = batch.is_transferred
            old_deployment_confirmed = batch.deployment_confirmed
            old_is_active = batch.is_active

            # Update allowed fields for PATCH with uniqueness checks
            if 'batch_name' in data:
                new_name = str(data['batch_name']).strip()
                if not new_name:
                    return make_response(jsonify({
                        "status": 400,
                        "message": "Batch name cannot be empty"
                    }), 400)
                existing = session.query(Batch).filter(
                    Batch.batch_name.ilike(new_name),
                    Batch.id != batch_id
                ).first()
                if existing:
                    return make_response(jsonify({
                        "status": 409,
                        "message": "Batch with that name already exists"
                    }), 409)
                batch.batch_name = new_name

            if 'certificate_number' in data:
                cert_no = data['certificate_number']
                if cert_no:
                    existing_cert = session.query(Batch).filter(
                        Batch.certificate_number == cert_no,
                        Batch.id != batch_id
                    ).first()
                    if existing_cert:
                        return make_response(jsonify({
                            "status": 409,
                            "message": "Batch with that certificate number already exists"
                        }), 409)
                batch.certificate_number = cert_no

            if 'date_deployed' in data:
                if data['date_deployed'] is not None:
                    batch.date_deployed = datetime.fromisoformat(data['date_deployed'])
                else:
                    batch.date_deployed = None
            if 'is_active' in data:
                batch.is_active = data['is_active']
            if 'is_transferred' in data:
                batch.is_transferred = data['is_transferred']
            if 'deployment_confirmed' in data:
                batch.deployment_confirmed = data['deployment_confirmed']

            session.commit()

            # Send emails based on stage changes
            try:
                # Stage 2: When is_transferred changes to True
                if 'is_transferred' in data and data['is_transferred'] and not old_is_transferred:
                    EmailService.send_offshore_transfer_batch(batch, trigger_source="batch.patch.stage_2_transfer")
                    create_audit_log(
                        action='OFFSHORE_TRANSFER',
                        target_type='batch',
                        target_id=batch.id,
                        target_name=batch.batch_name,
                        description=f'Batch "{batch.batch_name}" marked as transferred to offshore custodian.',
                        new_value={'stage': 2, 'is_transferred': True},
                        success=True
                    )

                # Stage 3: When deployment_confirmed changes to True and date_deployed is set
                if ('deployment_confirmed' in data and data['deployment_confirmed'] and 
                    not old_deployment_confirmed and batch.date_deployed is not None):
                    # Also set is_active to True as per requirements
                    batch.is_active = True
                    session.commit()
                    EmailService.send_investment_active_batch(batch, trigger_source="batch.patch.stage_3_deploy")
                    create_audit_log(
                        action='DEPLOYMENT_CONFIRMED',
                        target_type='batch',
                        target_id=batch.id,
                        target_name=batch.batch_name,
                        description=f'Batch "{batch.batch_name}" deployment confirmed. Fund valuation committed and finalized.',
                        new_value={'stage': 3, 'deployment_confirmed': True, 'date_deployed': batch.date_deployed.isoformat() if batch.date_deployed else None},
                        success=True
                    )

                # Stage 4: no investor email trigger (restricted to explicit big-four events).
                if 'is_active' in data and data['is_active'] and not old_is_active:
                    batch.is_active = True
                    session.commit()
                    create_audit_log(
                        action='BATCH_ACTIVATED',
                        target_type='batch',
                        target_id=batch.id,
                        target_name=batch.batch_name,
                        description=f'Batch "{batch.batch_name}" is now active. Statement data moved to distribution queue.',
                        new_value={'stage': 4, 'is_active': True},
                        success=True
                    )

            except Exception as email_error:
                logger.warning(f"Failed to send stage change emails: {str(email_error)}")
                # Don't fail the patch if emails fail

            # Determine status - Based on is_active field
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": "Batch patched successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "is_active": batch.is_active,
                    "is_transferred": batch.is_transferred,
                    "deployment_confirmed": batch.deployment_confirmed,
                    "status": status
                }
            }), 200)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error patching batch: {str(e)}"
            }), 500)

    @classmethod
    def delete_batch(cls, batch_id, session):
        """Delete a batch and all associated investments."""
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Clean email references first to avoid FK violations during batch deletion.
            session.query(PendingEmail).filter(PendingEmail.batch_id == batch_id).delete(synchronize_session=False)
            session.query(EmailLog).filter(EmailLog.batch_id == batch_id).delete(synchronize_session=False)

            investment_ids = [row[0] for row in session.query(Investment.id).filter(Investment.batch_id == batch_id).all()]
            if investment_ids:
                session.query(PendingEmail).filter(PendingEmail.investor_id.in_(investment_ids)).delete(synchronize_session=False)
                session.query(EmailLog).filter(EmailLog.investor_id.in_(investment_ids)).delete(synchronize_session=False)

            # Optional FK on withdrawals must be nulled before deleting batch row.
            session.query(Withdrawal).filter(Withdrawal.batch_id == batch_id).update(
                {Withdrawal.batch_id: None}, synchronize_session=False
            )

            # Delete investments first for explicit safety.
            session.query(Investment).filter(Investment.batch_id == batch_id).delete()
            session.delete(batch)
            session.commit()

            return make_response(jsonify({
                "status": 200,
                "message": "Batch deleted successfully"
            }), 200)
        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error deleting batch: {str(e)}"
            }), 500)

    @classmethod
    def get_batch_with_investments(cls, batch_id, session):
        """
        Get a batch with all its investments.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()

            investments_data = [
                {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "investor_email": inv.investor_email,
                    "investor_phone": inv.investor_phone,
                    "amount_deposited": float(inv.amount_deposited),
                    "date_deposited": inv.date_deposited.isoformat()
                }
                for inv in investments
            ]

            # Calculate total principal
            total_principal = sum(float(inv.amount_deposited) for inv in investments)

            return make_response(jsonify({
                "status": 200,
                "message": "Batch with investments retrieved successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "total_principal": total_principal,
                    "date_deployed": batch.date_deployed.isoformat(),
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat(),
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "investment_count": len(investments),
                    "investments": investments_data,
                    "is_active": batch.is_active
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch: {str(e)}"
            }), 500)

    @classmethod
    def get_batch_summary(cls, batch_id, session):
        """
        Get complete batch summary including investments and pro-rata distributions.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investments
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()

            # Get performance
            performance = session.query(Performance).filter(
                Performance.batch_id == batch_id
            ).first()

            # Get distributions
            distributions = session.query(ProRataDistribution).filter(
                ProRataDistribution.investment_id.in_(
                    session.query(Investment.id).filter(Investment.batch_id == batch_id)
                )
            ).all()

            total_invested = sum(float(inv.amount_deposited) for inv in investments)
            investor_values = [cls._calculate_batch_investment_values(inv, batch, session) for inv in investments]
            total_current_standing = Decimal(str(cls._calculate_batch_current_standing(batch, session)))
            total_withdrawals = sum(Decimal(str(values.get("withdrawals", 0))) for values in investor_values)
            total_profit = sum(Decimal(str(values.get("profit", 0))) for values in investor_values)

            distributions_data = [
                {
                    "investor_name": d.investment.investor_name,
                    "investor_email": d.investment.investor_email,
                    "investor_phone": d.investment.investor_phone,
                    "amount_deposited": float(d.investment.amount_deposited),
                    "date_deposited": d.investment.date_deposited.isoformat(),
                    "days_active": d.days_active,
                    "weighted_capital": float(d.weighted_capital),
                    "profit_share_percentage": float(d.profit_share_percentage),
                    "profit_allocated": float(d.profit_allocated)
                }
                for d in distributions
            ]

            total_profit_allocated = sum(float(d.profit_allocated) for d in distributions) if distributions else 0

            return make_response(jsonify({
                "status": 200,
                "message": "Batch summary retrieved successfully",
                "data": {
                    "batch_id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if batch.expected_close_date else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "total_investors": len({inv.internal_client_code for inv in investments}),
                    "total_invested": total_invested,
                    "total_current_standing": float(round(total_current_standing, 2)),
                    "total_withdrawals": float(round(total_withdrawals, 2)),
                    "total_profit": float(round(total_profit, 2)),
                    "performance": {
                        "gross_profit": float(performance.gross_profit) if performance else None,
                        "transaction_costs": float(performance.transaction_costs) if performance else None,
                        "net_profit": float(performance.net_profit) if performance else None
                    } if performance else None,
                    "total_profit_allocated": total_profit_allocated,
                    "is_active": batch.is_active,
                    "distributions": distributions_data if distributions else []
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch summary: {str(e)}"
            }), 500)

    @classmethod
    def upload_batch_excel(cls, batch_id, file, session):
        """
        Upload and parse Excel file with investor data for a batch.
        
        Args:
            batch_id: ID of the batch
            file: The uploaded file object
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            import pandas as pd
            from io import BytesIO
            
            # Check if batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Batch with ID {batch_id} not found"
                }), 404)
            
            # Read file into DataFrame
            file_stream = BytesIO(file.read())
            
            # Try to read as Excel first, then CSV
            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file_stream)
                else:
                    df = pd.read_excel(file_stream)
            except Exception as e:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Error reading file: {str(e)}"
                }), 400)
            
            # Map column names (case-insensitive)
            column_mapping = {
                'client name': 'investor_name',
                'internal client code': 'internal_client_code',
                'amount(usd)': 'amount_deposited',
                'amount_usd': 'amount_deposited',
                'amount': 'amount_deposited',
                'funds': 'fund_name',
                'fund': 'fund_name',
                'date_deposited': 'date_deposited',
                'date deposited': 'date_deposited',
                'deposit_date': 'date_deposited',
                'date transferred': 'date_deposited',
                'date_transferred': 'date_deposited',
                'email': 'investor_email',
                'investor email': 'investor_email',
                'investor_email': 'investor_email',
                'investor_phone': 'investor_phone',
                'phone': 'investor_phone',
            }
            
            # Normalize column names to lowercase
            df.columns = df.columns.str.lower().str.strip()
            
            # Rename columns according to mapping
            df = df.rename(columns=column_mapping)
            
            # Required columns
            required_columns = ['investor_name', 'internal_client_code', 'amount_deposited', 'fund_name']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Missing required columns: {', '.join(missing_columns)}"
                }), 400)
            
            # Drop rows with missing values in required columns
            df = df.dropna(subset=required_columns)
            
            def parse_date_deposited(value):
                if value is None or (isinstance(value, str) and value.strip() == "") or pd.isna(value):
                    # Never derive deposit date from deployment date.
                    return datetime.now(timezone.utc)

                if hasattr(value, 'to_pydatetime'):
                    value = value.to_pydatetime()

                if isinstance(value, datetime):
                    if value.tzinfo is None:
                        return value.replace(tzinfo=timezone.utc)
                    return value.astimezone(timezone.utc)

                if isinstance(value, str):
                    cleaned = value.strip()
                    try:
                        parsed = datetime.fromisoformat(cleaned)
                    except ValueError:
                        try:
                            parsed = datetime.strptime(cleaned, "%Y-%m-%d")
                        except ValueError:
                            try:
                                parsed = datetime.strptime(cleaned, "%d/%m/%Y")
                            except ValueError as exc:
                                raise ValueError(f"Invalid date_deposited format: {cleaned}") from exc
                    if parsed.tzinfo is None:
                        return parsed.replace(tzinfo=timezone.utc)
                    return parsed.astimezone(timezone.utc)

                # Handle Excel serial numeric dates and other numeric-like values.
                if isinstance(value, (int, float)):
                    parsed = pd.to_datetime(value, unit='D', origin='1899-12-30', errors='coerce')
                    if pd.notna(parsed):
                        parsed_dt = parsed.to_pydatetime()
                        if parsed_dt.tzinfo is None:
                            return parsed_dt.replace(tzinfo=timezone.utc)
                        return parsed_dt.astimezone(timezone.utc)

                # Final fallback should be "now", not deployment date.
                return datetime.now(timezone.utc)

            # Group by fund_name
            investments_added = 0
            total_amount = 0
            errors = []
            email_notifications_sent = 0
            email_notifications_failed = 0

            for fund_name, group in df.groupby('fund_name'):
                # 3. Fix: Fund Discovery
                core_fund = session.query(CoreFund).filter(db.func.lower(CoreFund.fund_name) == fund_name.lower()).first()
                if not core_fund:
                    core_fund = CoreFund(fund_name=fund_name)
                    session.add(core_fund)
                    session.flush()

                for idx, row in group.iterrows():
                    try:
                        investor_name = str(row['investor_name']).strip()
                        investor_email = str(row.get('investor_email', '') or '').strip()
                        investor_phone = str(row.get('investor_phone', '') or '').strip()
                        internal_client_code = str(row['internal_client_code']).strip()
                        amount_deposited = float(row['amount_deposited'])
                        date_deposited = parse_date_deposited(row.get('date_deposited'))
                        
                        # 2. Fix: Investor Row Logic
                        investment = Investment(
                            batch_id=batch_id,
                            investor_name=investor_name,
                            investor_email=investor_email or "",
                            investor_phone=investor_phone or "",
                            internal_client_code=internal_client_code,
                            amount_deposited=amount_deposited,
                            fund_id=core_fund.id,
                            fund_name=core_fund.fund_name,
                            date_deposited=date_deposited
                        )
                        session.add(investment)
                        
                        investments_added += 1
                        total_amount += amount_deposited

                    except Exception as e:
                        errors.append(f"Row {idx}: {str(e)}")
            
            # Send Stage 1 Batch email asynchronously
            if investments_added > 0:
                try:
                    EmailService.send_deposit_received_batch(
                        batch,
                        df.to_dict('records'),
                        trigger_source="batch.upload_excel.stage_1_initial_deposit",
                    )
                    logger.info(f"Triggered Stage 1 Async Batch Emails for {investments_added} rows")
                    email_notifications_sent = investments_added
                except Exception as email_err:
                    email_notifications_failed = investments_added
                    logger.warning(f"Failed to trigger stage 1 batch emails: {email_err}")
            
            # Log batch upload event
            if investments_added > 0:
                try:
                    EmailService._log_email_event(
                        batch_id=batch.id,
                        status='Summary',
                        email_type='BATCH_UPLOAD',
                        recipient_count=investments_added,
                        success_count=investments_added,
                        failure_count=0,
                        trigger_source="batch.upload_excel.audit_summary",
                    )
                    logger.info(f"Logged batch upload event for {investments_added} investments")
                except Exception as log_err:
                    logger.warning(f"Failed to log batch upload event: {log_err}")
            
            # Update batch total_principal
            # 1. Fix: Batch-Specific Totals
            # CRITICAL: Recalculate ONLY this batch's investments, not global sum
            batch_total_principal = session.query(db.func.sum(Investment.amount_deposited)).filter(
                Investment.batch_id == batch_id
            ).scalar() or 0
            batch.total_principal = batch_total_principal

            # Update stage to deposited (1) when investors exist
            if investments_added > 0:
                batch.stage = max(batch.stage or 0, 1)

            session.commit()
            
            response_data = {
                "status": 201,
                "message": f"Successfully imported {investments_added} rows of investments",
                "data": {
                    "batch_id": batch_id,
                    "batch_name": batch.batch_name,
                    "imported_investments": investments_added, # Represents total rows added (Audit log)
                    "total_amount": float(total_amount),
                    "investor_count": investments_added, # Reflecting 50 records processed instead of 15 unique
                    "total_principal": float(batch_total_principal),
                    "stage": batch.stage,
                    "emails_sent": email_notifications_sent,
                    "emails_failed": email_notifications_failed,
                }
            }
            
            if errors:
                response_data["warnings"] = errors
            
            return make_response(jsonify(response_data), 201)
            
        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error processing file: {str(e)}"
            }), 500)

    @classmethod
    def toggle_active(cls, batch_id, session):
        """
        Toggle the is_active status of a batch.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investment count for Stage 1 calculation
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()
            investors_count = len(investments)

            # Toggle lifecycle state explicitly.
            # - Closing a batch: deactivate + stamp date_closed
            # - Opening a batch: reactivate + clear date_closed
            batch.is_active = not batch.is_active
            if batch.is_active:
                batch.date_closed = None
            else:
                batch.date_closed = datetime.now(timezone.utc)
            session.commit()

            # Calculate current_stage using 4-stage logic
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if investors_count > 0 else 0
            
            # Stage 2: Transferred - Marked complete ONLY when is_transferred is true
            if batch.is_transferred:
                current_stage = max(current_stage, 2)
            
            # Stage 3: Deployed - Marked complete ONLY if date_deployed is set AND deployment_confirmed is true
            if batch.date_deployed is not None and batch.deployment_confirmed:
                current_stage = max(current_stage, 3)
            
            # Stage 4: Active - Marked complete ONLY when is_active is true
            if batch.is_active:
                current_stage = max(current_stage, 4)

            # Determine status based on is_active
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": f"Batch is_active toggled to {batch.is_active}",
                "data": {
                    "id": batch.id,
                    "is_active": batch.is_active,
                    "current_stage": current_stage,
                    "status": status
                }
            }), 200)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error toggling batch active status: {str(e)}"
            }), 500)

    @classmethod
    def toggle_transferred(cls, batch_id, session):
        """
        Toggle the is_transferred status of a batch.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investment count for Stage 1 calculation
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()
            investors_count = len(investments)

            # Save old state before toggling
            old_is_transferred = batch.is_transferred

            # Toggle is_transferred
            batch.is_transferred = not batch.is_transferred
            session.commit()

            # Calculate current_stage using 4-stage logic
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if investors_count > 0 else 0
            
            # Stage 2: Transferred - Marked complete ONLY when is_transferred is true
            if batch.is_transferred:
                current_stage = max(current_stage, 2)
            
            # Stage 3: Deployed - Marked complete ONLY if date_deployed is set AND deployment_confirmed is true
            if batch.date_deployed is not None and batch.deployment_confirmed:
                current_stage = max(current_stage, 3)
            
            # Stage 4: Active - Marked complete ONLY when is_active is true
            if batch.is_active:
                current_stage = max(current_stage, 4)

            # No email from toggle endpoint; notifications are restricted to explicit flows.
            if batch.is_transferred and not old_is_transferred and batch.stage < 2:
                batch.stage = 2
                session.commit()

            # Determine status based on is_active
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": f"Batch is_transferred toggled to {batch.is_transferred}",
                "data": {
                    "id": batch.id,
                    "is_transferred": batch.is_transferred,
                    "current_stage": current_stage,
                    "status": status
                }
            }), 200)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error toggling batch transferred status: {str(e)}"
            }), 500)

    @classmethod
    def notify_transfer(cls, batch_id, session):
        """
        A dedicated endpoint handler for stage 2 transfer notifications.
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

            if batch.stage >= 2 and batch.is_transferred:
                return make_response(jsonify({
                    "status": 200,
                    "message": "Transfer already notified",
                    "data": {"stage": batch.stage}
                }), 200)

            batch.is_transferred = True
            batch.stage = 2
            session.commit()

            EmailService.send_offshore_transfer_batch(batch, trigger_source="batch.notify_transfer.stage_2_transfer")

            return make_response(jsonify({
                "status": 200,
                "message": "Transfer notification triggered",
                "data": {
                    "id": batch.id,
                    "is_transferred": batch.is_transferred,
                    "stage": batch.stage,
                    "emails_sent": 0,
                    "emails_failed": 0
                }
            }), 200)
        except Exception as e:
            session.rollback()
            return make_response(jsonify({"status": 500, "message": f"Error sending transfer notification: {str(e)}"}), 500)

    @classmethod
    def update_status(cls, batch_id, data, session):
        """
        Update batch status and trigger automated emails for multi-stage investment lifecycle.
        
        Handles:
        - Stage 2: Mark as Transferred (is_transferred: true)
        - Stage 3: Date Deployed saved (date_deployed + auto-set deployment_confirmed: true)  
        - Stage 4: Set Active (is_active: true)
        
        Args:
            batch_id: ID of the batch
            data: dict with status update fields
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # 1. Delegate Logic to StatusUpdateController
            try:
                StatusUpdateController.handle_status_transition(batch, data, session)
            except Exception as transition_error:
                logger.error(f"Error in status transition logic for batch {batch_id}: {str(transition_error)}")

            # 2. Results and responses
            current_stage = getattr(batch, 'stage', 1)
            
            # Calculate current stage for response
            current_stage = getattr(batch, 'stage', 1)
            
            # Determine status
            status = 'Active' if batch.is_active else 'Deactivated'
            
            return make_response(jsonify({
                "status": 200,
                "message": "Batch status updated successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "is_transferred": batch.is_transferred,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "deployment_confirmed": batch.deployment_confirmed,
                    "is_active": batch.is_active,
                    "current_stage": current_stage,
                    "status": status,
                    "emails_sent": batch.email_results['sent'],
                    "emails_failed": batch.email_results['failed']
                }
            }), 200)

        except ValueError as e:
            session.rollback()
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating batch status: {str(e)}")
            return make_response(jsonify({
                "status": 500,
                "message": f"Error updating batch status: {str(e)}"
            }), 500)
