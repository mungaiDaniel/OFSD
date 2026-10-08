from app.Batch.model import Batch
from app.Investments.model import (
    Investment, EpochLedger, Withdrawal, PendingEmail, EmailLog, FINAL_WITHDRAWAL_STATUSES,
    WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
)
from app.Valuation.model import Statement, ValuationRun, BatchValuation, InvestmentBatchValuation, DailyNAV
from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
from app.logic.valuation_service import _q2
from app.Batch.core_fund import CoreFund
from app.Funds.investor_shares import InvestorShares
from app.database.database import db
from app.utils.email_service import EmailService
from app.utils.audit_log import create_audit_log
from app.database.product_type import PRODUCT_TYPES, FUNDS, SHARES
from app.logic.shares_transfer_service import SharesTransferService, SharesTransferError
from app.logic.shares_deployment_service import SharesDeploymentService, SharesDeploymentError
from app.Funds.share_class import ShareClass
from flask import jsonify, make_response
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from marshmallow import ValidationError
from sqlalchemy import select, distinct, func, and_, or_, insert
from sqlalchemy.orm import aliased, joinedload
import json
from app.Batch.status_update_controller import StatusUpdateController
import logging

logger = logging.getLogger(__name__)


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
            share_class_id = data.get('share_class_id')
            is_open = data.get('is_open')

            # Resolve product_type (FUNDS or SHARES). When a share_class_id is given,
            # the share class's own product_type column is the single source of
            # truth (Task 8 — inherited from its CoreFund at creation, see
            # app/Funds/share_class.py) — an explicit product_type must agree with
            # it. Without a share_class_id yet (two-stage creation), fall back to
            # an explicit product_type or default to FUNDS, the overwhelmingly
            # common case; a SHARES batch created this way must have
            # share_class_id set (and therefore its real product_type resolved)
            # before it can accept deposits — see
            # BatchManagementService.add_investor_to_batch.
            requested_product_type = data.get('product_type')
            if requested_product_type is not None:
                requested_product_type = str(requested_product_type).strip().upper()
                if requested_product_type not in PRODUCT_TYPES:
                    return make_response(jsonify({
                        "status": 400,
                        "message": f"product_type must be one of {PRODUCT_TYPES}"
                    }), 400)

            product_type = requested_product_type or FUNDS
            if share_class_id is not None:
                share_class = session.query(ShareClass).filter(ShareClass.id == int(share_class_id)).first()
                if not share_class:
                    return make_response(jsonify({
                        "status": 400,
                        "message": f"Share class {share_class_id} not found"
                    }), 400)
                derived_product_type = share_class.product_type
                if requested_product_type and requested_product_type != derived_product_type:
                    return make_response(jsonify({
                        "status": 400,
                        "message": (
                            f"product_type '{requested_product_type}' does not match "
                            f"the share class's fund ({derived_product_type})"
                        )
                    }), 400)
                product_type = derived_product_type

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
                is_active=False,  # New batches start as inactive
                share_class_id=int(share_class_id) if share_class_id is not None else None,
                is_open=(bool(is_open) if is_open is not None else True),
                deployment_confirmed=False,
                stage=1,
                product_type=product_type,
            )

            batch.save(session)

            create_audit_log(
                action='BATCH_PRODUCT_TYPE_ASSIGNED',
                target_type='batch',
                target_id=batch.id,
                target_name=batch.batch_name,
                description=f'Batch "{batch.batch_name}" created as a {product_type} product.',
                new_value={'product_type': product_type},
                success=True,
            )

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
                    "share_class_id": batch.share_class_id,
                    "is_open": batch.is_open,
                    "product_type": batch.product_type,
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
    def get_batch_by_id(cls, batch_id, session, page=1, per_page=200, search=None, show_all=False):
        """
        Get a batch by ID with all details and investments.

        The investor-level detail lists (`investments` / `grouped_by_fund`) are only
        populated when `search` is provided, or `show_all` is explicitly set (the
        "Show all" toggle on the batch detail page — Task 6; the frontend then
        chunk-loads/virtualizes rather than rendering all rows at once). With
        neither, those lists come back empty and the page shows only batch-wide
        counts/totals — this is what keeps a 10,000-investor batch fast to open,
        since neither the full investment row set nor the per-investment
        valuation cascade is ever loaded just to render the batch header. All
        batch-wide totals (total_capital, investors_count, investment_rows_count,
        etc.) are computed via SQL aggregates, not by loading every row.

        Args:
            batch_id: ID of the batch
            session: database session
            page: 1-indexed page of investors to return in the detail lists (only
                relevant when `search` or `show_all` is set)
            per_page: investors per page (capped at 1000)
            search: optional text match against client code / email / phone —
                when omitted (and show_all is False), no investor rows are returned
            show_all: bypass the "no search -> empty list" gate and paginate
                through every investor in the batch instead (still paginated —
                this never loads more than one page's worth of rows per call)

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

            page = max(int(page or 1), 1)
            per_page = min(max(int(per_page or 200), 1), 1000)
            search = (search or "").strip()

            # Cheap SQL aggregate — never loads investment rows just to count them.
            total_investment_rows = session.query(func.count(Investment.id)).filter(
                Investment.batch_id == batch_id
            ).scalar() or 0

            latest_deposit_date = session.query(func.max(Investment.date_deposited)).filter(
                Investment.batch_id == batch_id
            ).scalar()

            if search or show_all:
                base_query = session.query(Investment).filter(Investment.batch_id == batch_id)
                if search:
                    like = f"%{search}%"
                    base_query = base_query.filter(
                        or_(
                            Investment.internal_client_code.ilike(like),
                            Investment.investor_email.ilike(like),
                            Investment.investor_phone.ilike(like),
                        ),
                    )
                match_count = base_query.count()
                total_pages = max((match_count + per_page - 1) // per_page, 1)
                page = min(page, total_pages)
                start = (page - 1) * per_page
                investments = base_query.order_by(Investment.id.asc()).offset(start).limit(per_page).all()
                pagination_total = match_count
            else:
                total_pages = 1
                page = 1
                investments = []
                pagination_total = 0

            # Only run the expensive per-investment valuation cascade for the page being
            # displayed (search results only), not the whole batch — the batch-wide total
            # below comes from batch.cached_total_capital instead (kept fresh at write
            # time; see BatchController.refresh_cached_total_capital), not from summing
            # every investment on every read.
            epoch_data = {}
            prefetch = cls._prefetch_valuation_cascade(session, investments)
            for inv in investments:
                epoch_data[inv.id] = cls._calculate_batch_investment_values(inv, batch, session, **prefetch)

            investments_data = [
                {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    "original_principal": float(inv.amount_deposited),
                    "deployment_fee_deducted": float(inv.deployment_fee_deducted or 0),
                    "transaction_fee_usd": float(inv.transfer_fee_deducted or 0),
                    "entry_fee_usd": float(inv.deployment_fee_deducted or 0),
                    "deployment_fee": float(inv.transfer_fee_deducted or 0),
                    "main_balance": float(inv.net_principal),
                    # Task 6 — SHARES-only columns on the batch client list/export.
                    # net_usd deliberately NOT net_principal (which also subtracts
                    # any oversubscription refund — shown separately below).
                    "net_usd": float(
                        (inv.amount_deposited or 0) - (inv.deployment_fee_deducted or 0) - (inv.transfer_fee_deducted or 0)
                    ),
                    "net_ngn": float(inv.net_ngn) if inv.net_ngn is not None else None,
                    "refund_usd": float(inv.oversubscription_refund_amount) if inv.oversubscription_refund_amount else None,
                    "status": "Active" if batch.is_transferred else "Pending",
                    # Prefer the FK relationship fund name, fall back to the legacy fund_name field
                    "fund_id": inv.fund_id,
                    "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                    "share_class_id": inv.share_class_id,
                    "class_code": inv.share_class.class_code if inv.share_class else None,
                    "class_currency": inv.share_class.currency if inv.share_class else None,
                    "shares_owned": float(inv.shares_owned) if inv.shares_owned is not None else None,
                    "previous_nav_price": float(inv.previous_nav_price) if inv.previous_nav_price is not None else None,
                    "opening_market_value": float(inv.opening_market_value) if inv.opening_market_value is not None else None,
                    "date_deposited": inv.date_deposited.isoformat() if inv.date_deposited else None,
                    "opening_balance": epoch_data[inv.id]["opening_balance"],
                    "current_balance": epoch_data[inv.id]["current_balance"],
                    "market_value": epoch_data[inv.id]["current_balance"],
                    "performance_pct": epoch_data[inv.id].get("performance_pct"),
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
                    "original_principal": float(inv.amount_deposited),
                    "deployment_fee_deducted": float(inv.deployment_fee_deducted or 0),
                    "transaction_fee_usd": float(inv.transfer_fee_deducted or 0),
                    "entry_fee_usd": float(inv.deployment_fee_deducted or 0),
                    "deployment_fee": float(inv.transfer_fee_deducted or 0),
                    "main_balance": float(inv.net_principal),
                    "net_usd": float(
                        (inv.amount_deposited or 0) - (inv.deployment_fee_deducted or 0) - (inv.transfer_fee_deducted or 0)
                    ),
                    "net_ngn": float(inv.net_ngn) if inv.net_ngn is not None else None,
                    "refund_usd": float(inv.oversubscription_refund_amount) if inv.oversubscription_refund_amount else None,
                    "status": "Active" if batch.is_transferred else "Pending",
                    "fund_id": inv.fund_id,
                    "fund_name": fund_name,
                    "share_class_id": inv.share_class_id,
                    "class_code": inv.share_class.class_code if inv.share_class else None,
                    "class_currency": inv.share_class.currency if inv.share_class else None,
                    "shares_owned": float(inv.shares_owned) if inv.shares_owned is not None else None,
                    "previous_nav_price": float(inv.previous_nav_price) if inv.previous_nav_price is not None else None,
                    "opening_market_value": float(inv.opening_market_value) if inv.opening_market_value is not None else None,
                    "market_value": epoch_data[inv.id]["current_balance"],
                    "performance_pct": epoch_data[inv.id].get("performance_pct"),
                    "withdrawals": epoch_data[inv.id]["withdrawals"],
                    "profit": epoch_data[inv.id]["profit"],
                }
                
                grouped_by_fund[fund_name].append(inv_data)
                fund_totals[fund_name] += float(inv.amount_deposited)

            # Calculate current_stage (1-4) based on specific conditions
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if total_investment_rows > 0 else 0
            
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

            # Total current standing — read from the cache kept fresh at write time (deploy,
            # withdrawal approval, valuation commit; see refresh_cached_total_capital) rather
            # than recomputed here on every read. Falls back to a live (slower) calculation
            # and self-heals the cache for batches that predate this cache or somehow missed
            # an invalidation — correctness is never sacrificed for speed.
            if batch.cached_total_capital is not None:
                total_current_standing = float(batch.cached_total_capital)
            else:
                total_current_standing = cls.refresh_cached_total_capital(batch, session)
            # Investment.net_principal is a Python @property (amount_deposited minus
            # both fee columns and any oversubscription refund), not a mapped column —
            # it can't be used inside a SQL expression, so it's inlined here as the
            # same subtraction over the underlying columns instead. This specific
            # expression (fees only, no refund) is "Net Principal" / "Net After Fees"
            # on the batch detail panel — the pipeline stage between the raw
            # Total Deposited figure and Total NAV, added so it's clear where money
            # went at each step (transfer cost first, then entry fee on the
            # remainder — same order the deployment flow itself applies them in).
            # Computed unconditionally (unlike Total NAV below) since fees are set
            # at Transfer stage, before deployment.
            net_principal_expr = (
                Investment.amount_deposited
                - func.coalesce(Investment.transfer_fee_deducted, 0)
                - func.coalesce(Investment.deployment_fee_deducted, 0)
            )
            total_net_principal = (
                session.query(func.sum(net_principal_expr))
                .filter(Investment.batch_id == batch_id)
                .scalar()
                or 0.0
            )

            computed_deployment_total_nav = None
            if batch.stage >= 3 and total_investment_rows > 0:
                computed_deployment_total_nav = session.query(
                    func.sum(func.coalesce(Investment.opening_market_value, net_principal_expr, 0))
                ).filter(Investment.batch_id == batch_id).scalar()

            # Count UNIQUE investors in this batch using DISTINCT on internal_client_code
            unique_investor_count = session.query(
                db.func.count(distinct(Investment.internal_client_code))
            ).filter(
                Investment.batch_id == batch_id
            ).scalar() or 0

            # Total investment entries across the WHOLE batch (50 rows = 50 transactions,
            # even if only 15 unique people) — not just the current page.
            investment_rows_count = total_investment_rows

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
            active_days = cls._calculate_active_days(batch)

            return make_response(jsonify({
                "status": 200,
                "message": "Batch retrieved successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "batch_type": batch_type,
                    "product_type": batch.product_type,
                    "total_principal": float(fresh_total_principal),
                    "total_net_principal": float(total_net_principal),
                    "total_capital": float(total_current_standing),
                    "date_deployed": effective_date.isoformat() if effective_date else None,
                    "duration_days": batch.duration_days,
                    "active_days": active_days,
                    "expected_close_date": (effective_date + timedelta(days=batch.duration_days)).isoformat() if effective_date else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "transaction_cost": float(batch.transaction_cost or 0),
                    "transfer_transaction_cost": float(batch.transfer_transaction_cost or 0),
                    "unique_investor_count": int(unique_investor_count),
                    "investment_rows_count": investment_rows_count,
                    "investors_count": int(unique_investor_count),
                    "is_active": batch.is_active,
                    "is_transferred": batch.is_transferred,
                    "deployment_confirmed": batch.deployment_confirmed,
                    "stage": current_stage,
                    "current_stage": current_stage,
                    "status": status,
                    "deployment_nav": float(batch.deployment_nav) if getattr(batch, "deployment_nav", None) is not None else None,
                    "total_shares": float(batch.total_shares) if getattr(batch, "total_shares", None) is not None else None,
                    "deployment_total_nav": (
                        float(computed_deployment_total_nav)
                        if computed_deployment_total_nav is not None
                        else (float(batch.deployment_total_nav) if getattr(batch, "deployment_total_nav", None) is not None else None)
                    ),
                    "deployment_breakdown": json.loads(batch.deployment_breakdown) if getattr(batch, "deployment_breakdown", None) else None,
                    "latest_deposit_date": latest_deposit_date.isoformat() if latest_deposit_date else None,
                    # is_dprp_fund tells the frontend whether to show the SHARES deployment
                    # form (exchange rate / price per share / shares allocated) instead of
                    # the FUNDS NAV deployment form — equivalent to product_type == SHARES.
                    "is_dprp_fund": cls.is_batch_dprp_fund(batch, session),
                    "is_oversubscribed": bool(getattr(batch, "is_oversubscribed", False)),
                    "allocation_rate": float(batch.allocation_rate) if getattr(batch, "allocation_rate", None) is not None else None,
                    "shares_exchange_rate_ngn": float(batch.shares_exchange_rate_ngn) if getattr(batch, "shares_exchange_rate_ngn", None) is not None else None,
                    "shares_price_per_share_ngn": float(batch.shares_price_per_share_ngn) if getattr(batch, "shares_price_per_share_ngn", None) is not None else None,
                    "shares_allocated_total": batch.shares_allocated_total,
                    "shares_demand_total": batch.shares_demand_total,
                    "shares_unallocated_total": batch.shares_unallocated_total,
                    "investments": investments_data,  # Flat array — only populated when `search` is set
                    "grouped_by_fund": grouped_by_fund_response,  # Only populated when `search` is set
                    "investments_pagination": {
                        "page": page, "per_page": per_page,
                        "total": pagination_total, "total_pages": total_pages,
                    },
                    "created_at": batch.date_created.isoformat() if hasattr(batch, 'date_created') else None
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch: {str(e)}"
            }), 500)

    @classmethod
    def get_batch_investments_light(cls, batch_id, session):
        """
        Full investor list for a batch, but only the cheap direct-column fields
        (no per-investment valuation cascade) — used exclusively by the
        Transfer/Deploy stage-transition modals, which need every investment in
        the batch (to group by share class and sum deposits) but only run once
        per stage change, not on every page view.
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).order_by(Investment.id.asc()).all()

            data = [
                {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    "main_balance": float(inv.net_principal) if inv.net_principal is not None else float(inv.amount_deposited),
                    "share_class_id": inv.share_class_id,
                    "class_code": inv.share_class.class_code if inv.share_class else None,
                    "class_currency": inv.share_class.currency if inv.share_class else None,
                }
                for inv in investments
            ]
            return make_response(jsonify({"status": 200, "count": len(data), "data": data}), 200)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch investments: {str(e)}"
            }), 500)

    @classmethod
    def _to_utc(cls, dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _calculate_active_days(cls, batch):
        """Compute active days from persisted deployment/close dates."""
        if not batch or batch.date_deployed is None:
            return 0
        start_dt = cls._to_utc(batch.date_deployed)
        end_dt = cls._to_utc(batch.date_closed) if batch.date_closed else datetime.now(timezone.utc)
        if start_dt is None or end_dt is None:
            return 0
        if end_dt.date() < start_dt.date():
            return 0
        return (end_dt.date() - start_dt.date()).days + 1

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
                "amount": Decimal(str(related.net_principal)),
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
    def _siblings_same_client_fund(cls, session, inv: Investment) -> list:
        """All Investment rows for the same client code + fund (across batches)."""
        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        q = (
            session.query(Investment)
            .options(joinedload(Investment.batch))
            .filter(Investment.internal_client_code == inv.internal_client_code)
        )
        if inv.fund_id is not None:
            q = q.filter(Investment.fund_id == inv.fund_id)
        else:
            q = q.filter(
                func.lower(func.coalesce(Investment.fund_name, "")) == func.lower(fund_name or "")
            )
        return q.all()

    @classmethod
    def _epoch_ledger_attributed_balance(cls, inv, session):
        """
        EpochLedger is stored per (client, fund), not per batch. When the same client+fund
        appears in multiple batches, only the earliest deployment should absorb ledger totals
        for epochs that end *before* the next batch's deployment; later tranches are handled
        by BatchValuation / net principal (return None here).
        """
        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        if not fund_name:
            return None

        balance, _epoch_end = cls._epoch_ledger_attributed_balance_and_epoch_end(inv, session)
        return balance

    @classmethod
    def _epoch_ledger_attributed_balance_and_epoch_end(cls, inv, session):
        """
        EpochLedger is stored per (client, fund), not per batch.
        For investors with multiple batches for the same fund, only the earliest
        deployment should absorb ledger totals before the next batch deployment.

        Returns:
          (end_balance_decimal, epoch_end_datetime) or (None, None)
        """
        fund_name = inv.fund.fund_name if inv.fund else inv.fund_name
        if not fund_name:
            return None, None

        sibs = cls._siblings_same_client_fund(session, inv)
        if len(sibs) <= 1:
            le = (
                session.query(EpochLedger)
                .filter(
                    EpochLedger.internal_client_code == inv.internal_client_code,
                    func.lower(EpochLedger.fund_name) == func.lower(fund_name),
                )
                .order_by(EpochLedger.epoch_end.desc())
                .first()
            )
            if not le:
                return None, None
            return _q2(Decimal(str(le.end_balance or 0))), le.epoch_end

        sibs_sorted = sorted(
            sibs,
            key=lambda x: (
                cls._to_utc(x.batch.date_deployed)
                if x.batch and x.batch.date_deployed
                else datetime(9999, 12, 31, tzinfo=timezone.utc),
                x.id,
            ),
        )
        idx = next((i for i, x in enumerate(sibs_sorted) if x.id == inv.id), 0)
        if idx > 0:
            return None, None

        rows = (
            session.query(EpochLedger)
            .filter(
                EpochLedger.internal_client_code == inv.internal_client_code,
                func.lower(EpochLedger.fund_name) == func.lower(fund_name),
            )
            .order_by(EpochLedger.epoch_end.asc())
            .all()
        )
        if not rows:
            return None, None

        # Multiple tranches: only ledger rows on or before the next batch deployment.
        if len(sibs_sorted) > 1:
            nxt = sibs_sorted[1]
            cut = nxt.batch.date_deployed if nxt.batch else None
            if not cut:
                return None, None
            cut_dt = cls._to_utc(cut)
            eligible = [r for r in rows if cls._to_utc(r.epoch_end) <= cut_dt]
            if not eligible:
                return None, None
            last = eligible[-1]
            return _q2(Decimal(str(last.end_balance or 0))), last.epoch_end

        return None, None

    @classmethod
    def _prefetch_withdrawal_sums_for_batch(cls, session, investments) -> dict:
        """
        Bulk version of _withdrawals_for_investment_batch — one grouped query covering
        every investment in a batch instead of one query per investment. Returns
        {(internal_client_code, fund_id): Decimal}, matching the exact same filters
        (final-status, non-refund withdrawals) as the per-row version. NULL fund_id
        groups correctly under the (code, None) key, matching the per-row version's
        "both NULL counts as a match" rule with no extra logic needed.

        Pass the result as wd_prefetch= to _calculate_batch_investment_values (or
        _withdrawals_for_investment_batch directly) to skip its per-row query —
        this is what turns a batch-wide recompute from N withdrawal queries into 1.
        """
        client_codes = {inv.internal_client_code for inv in investments if inv.internal_client_code}
        if not client_codes:
            return {}
        rows = (
            session.query(
                Withdrawal.internal_client_code,
                Withdrawal.fund_id,
                func.coalesce(func.sum(Withdrawal.amount), 0),
            )
            .filter(
                Withdrawal.internal_client_code.in_(client_codes),
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            )
            .group_by(Withdrawal.internal_client_code, Withdrawal.fund_id)
            .all()
        )
        return {(code, fund_id): Decimal(str(total or 0)) for code, fund_id, total in rows}

    @classmethod
    def _prefetch_withdrawal_details_for_batch(cls, session, investments) -> dict:
        """
        Like _prefetch_withdrawal_sums_for_batch, but keeps each individual
        withdrawal's (date_withdrawn, amount) instead of a pre-summed total —
        _uncaptured_withdrawals_for_investment_batch needs to filter by a
        per-row-varying since_dt (the investment's own latest valuation date),
        which a single pre-summed total can't do. Returns
        {(client_code, fund_id): [(date_withdrawn, amount), ...]}.
        """
        client_codes = {inv.internal_client_code for inv in investments if inv.internal_client_code}
        if not client_codes:
            return {}
        rows = (
            session.query(
                Withdrawal.internal_client_code,
                Withdrawal.fund_id,
                Withdrawal.date_withdrawn,
                Withdrawal.amount,
            )
            .filter(
                Withdrawal.internal_client_code.in_(client_codes),
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            )
            .all()
        )
        detail = {}
        for code, fund_id, date_withdrawn, amount in rows:
            detail.setdefault((code, fund_id), []).append((date_withdrawn, amount))
        return detail

    @classmethod
    def _prefetch_investor_shares_for_batch(cls, session, investments) -> dict:
        """One query's worth of InvestorShares for every investment, keyed by
        investment_id — see _calculate_batch_investment_values's shares_prefetch."""
        from app.Funds.investor_shares import InvestorShares
        investment_ids = [inv.id for inv in investments]
        if not investment_ids:
            return {}
        rows = session.query(InvestorShares).filter(InvestorShares.investment_id.in_(investment_ids)).all()
        return {r.investment_id: r for r in rows}

    @classmethod
    def _prefetch_latest_valuation_snapshots(cls, session, investor_shares_ids) -> dict:
        """Latest ValuationSnapshot per investor_shares_id, keyed by investor_shares_id —
        see _calculate_batch_investment_values's snapshot_prefetch. Fetches every
        snapshot for the given ids in one query and reduces to the latest per group
        in Python (a correlated-subquery/window-function version would be one more
        round trip either way, and batches don't yet have enough snapshot HISTORY
        per position for this list to be large)."""
        from app.Valuation.valuation_snapshot import ValuationSnapshot
        ids = list(investor_shares_ids)
        if not ids:
            return {}
        rows = (
            session.query(ValuationSnapshot)
            .filter(ValuationSnapshot.investor_shares_id.in_(ids))
            .order_by(ValuationSnapshot.investor_shares_id, ValuationSnapshot.valuation_date.desc())
            .all()
        )
        latest_by_id = {}
        for snap in rows:
            if snap.investor_shares_id not in latest_by_id:
                latest_by_id[snap.investor_shares_id] = snap
        return latest_by_id

    @classmethod
    def _withdrawals_for_investment_batch(cls, session, inv: Investment, batch_id: int, wd_prefetch: dict = None) -> Decimal:
        """
        Withdrawals attributed to this investment row within a batch (atomic isolation).

        Excludes oversubscription-refund withdrawals: that money was never actually
        deployed into the fund (Investment.net_principal already reflects the reduction
        via oversubscription_refund_amount at deployment time), so subtracting it again
        here once the refund is approved would double-count it.

        wd_prefetch: optional {(client_code, fund_id): Decimal} from
        _prefetch_withdrawal_sums_for_batch — when provided (even if this specific
        key has no withdrawals and so isn't in it, the overwhelmingly common case),
        used instead of running this method's own per-row query. A missing key
        means zero withdrawals, not "prefetch didn't cover this row" — the dict is
        built from every investment passed to _prefetch_withdrawal_sums_for_batch,
        so any key not in it genuinely has no matching withdrawal rows.
        """
        if wd_prefetch is not None:
            return wd_prefetch.get((inv.internal_client_code, inv.fund_id), Decimal("0"))

        Inv = aliased(Investment)
        fund_match = or_(
            and_(Inv.fund_id.isnot(None), Inv.fund_id == Withdrawal.fund_id),
            and_(Inv.fund_id.is_(None), Withdrawal.fund_id.is_(None)),
        )
        q = (
            session.query(func.coalesce(func.sum(Withdrawal.amount), 0))
            .select_from(Withdrawal)
            .join(
                Inv,
                and_(
                    Inv.internal_client_code == Withdrawal.internal_client_code,
                    Inv.batch_id == batch_id,
                    Inv.id == inv.id,
                    fund_match,
                ),
            )
            .filter(
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            )
        )
        return Decimal(str(q.scalar() or 0))

    @classmethod
    def _uncaptured_withdrawals_for_investment_batch(
        cls,
        session,
        inv: Investment,
        batch_id: int,
        since_dt,
        wd_detail_prefetch: dict = None,
    ) -> Decimal:
        """Withdrawals after the last valuation snapshot date for this investment+batch.
        Same oversubscription-refund exclusion as _withdrawals_for_investment_batch.

        wd_detail_prefetch: optional {(client_code, fund_id): [(date, amount), ...]}
        from _prefetch_withdrawal_details_for_batch — when provided, sums in Python
        instead of running this method's own per-row query.
        """
        if wd_detail_prefetch is not None:
            rows = wd_detail_prefetch.get((inv.internal_client_code, inv.fund_id), [])
            if since_dt is not None:
                rows = [r for r in rows if r[0] is not None and r[0] > since_dt]
            return Decimal(str(sum((Decimal(str(amt or 0)) for _dt, amt in rows), Decimal("0"))))

        Inv = aliased(Investment)
        fund_match = or_(
            and_(Inv.fund_id.isnot(None), Inv.fund_id == Withdrawal.fund_id),
            and_(Inv.fund_id.is_(None), Withdrawal.fund_id.is_(None)),
        )
        q = (
            session.query(func.coalesce(func.sum(Withdrawal.amount), 0))
            .select_from(Withdrawal)
            .join(
                Inv,
                and_(
                    Inv.internal_client_code == Withdrawal.internal_client_code,
                    Inv.batch_id == batch_id,
                    Inv.id == inv.id,
                    fund_match,
                ),
            )
            .filter(
                Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
            )
        )
        if since_dt is not None:
            q = q.filter(Withdrawal.date_withdrawn > since_dt)
        return Decimal(str(q.scalar() or 0))

    @classmethod
    def _latest_nav_for_series(cls, session, share_series: str, as_of_dt=None):
        if not share_series:
            return None
        q = session.query(DailyNAV).filter(DailyNAV.share_series == share_series)
        if as_of_dt is not None:
            q = q.filter(DailyNAV.nav_date <= as_of_dt)
        res = q.order_by(DailyNAV.nav_date.desc()).first()
        if res:
            return res
        try:
            from app.Funds.nav_history import NavHistory
            from app.Funds.share_class import ShareClass
            nq = session.query(NavHistory).join(ShareClass, NavHistory.share_class_id == ShareClass.id).filter(
                or_(
                    ShareClass.class_code.ilike(share_series),
                    ShareClass.class_name.ilike(share_series),
                )
            )
            if as_of_dt is not None:
                as_of_date = as_of_dt.date() if hasattr(as_of_dt, 'date') else as_of_dt
                nq = nq.filter(NavHistory.nav_date <= as_of_date)
            latest_nh = nq.order_by(NavHistory.nav_date.desc()).first()
            if latest_nh:
                class _NavWrapper:
                    def __init__(self, price, dt):
                        self.nav_price = price
                        self.nav_date = dt
                return _NavWrapper(latest_nh.nav_per_share, latest_nh.nav_date)
        except Exception:
            pass
        return None

    @classmethod
    def _recalculate_shares_on_deploy(cls, batch, session):
        """DEPRECATED: Use deploy_batch for new share-based deployment flow."""
        if batch is None or batch.date_deployed is None:
            return
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        for inv in investments:
            series = inv.share_series or (inv.fund.fund_name if inv.fund else inv.fund_name)
            if not series:
                continue
            nav_row = cls._latest_nav_for_series(session, series, batch.date_deployed)
            if not nav_row or Decimal(str(nav_row.nav_price or 0)) <= 0:
                continue
            starting_nav = Decimal(str(nav_row.nav_price))
            inv.share_series = series
            inv.shares_owned = (Decimal(str(inv.net_principal)) / starting_nav).quantize(Decimal("0.0001"))
            session.add(inv)

    @classmethod
    def is_batch_dprp_fund(cls, batch, session=None) -> bool:
        """
        Whether a batch is DPRP (Dangote Petroleum Refinery and Petrochemicals) —
        the only SHARES product today. Used to be a query joining through
        investments/core_funds and re-running is_dangote_dprp_fund per call;
        product_type (set once at batch creation — see
        BatchManagementService._create_new_batch) already IS that same
        classification, so this is now just a field check. `session` is accepted
        and ignored for backward compatibility with existing callers.
        """
        return batch is not None and batch.product_type == SHARES

    @classmethod
    def _on_batch_transferred(cls, batch, session):
        """
        Product-specific hook fired once a batch transitions to Stage 2
        (Transferred) — see patch_batch. Shares batches use the exact same
        stage-transition code as Funds batches (no separate state machine);
        this hook is where behaviour that differs by product_type branches off.

        Empty for now — Task 2 (FUNDS) and Task 3 (SHARES) fill these in.
        """
        if batch.product_type == SHARES:
            pass
        else:
            pass

    @classmethod
    def _on_batch_deployed(cls, batch, session):
        """
        Product-specific hook fired once a batch transitions to Stage 3
        (Deployed) — see patch_batch. Mirrors _on_batch_transferred above.

        Empty for now — Task 2 (FUNDS) and Task 3 (SHARES) fill these in.
        """
        if batch.product_type == SHARES:
            pass
        else:
            pass

    @classmethod
    def _deploy_shares_for_batch(cls, batch, session):
        """
        Create or update InvestorShares for deployed batch investments —
        FUNDS (NAV-based) only. SHARES batches are deployed by
        SharesDeploymentService (Task 3), which computes whole shares from a
        price-per-share/exchange-rate, not a NAV.
        """
        if batch is None or batch.date_deployed is None:
            return

        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        if not investments:
            return

        deployment_date = batch.deployment_date_actual or batch.date_deployed.date()

        breakdown_by_id = {}
        breakdown_by_code = {}
        targets_by_id = {}
        targets_by_code = {}

        if getattr(batch, "deployment_breakdown", None):
            try:
                parsed = json.loads(batch.deployment_breakdown)
                if isinstance(parsed, list):
                    for entry in parsed:
                        if not isinstance(entry, dict):
                            continue
                        share_class_id = entry.get("share_class_id")
                        class_code = entry.get("class_code")
                        nav_per_share = Decimal(str(entry.get("navPerShare", 0)))
                        total_shares = Decimal(str(entry.get("totalShares", 0)))
                        total_nav = Decimal(str(entry.get("totalNav", 0)))
                        if share_class_id is not None:
                            breakdown_by_id[int(share_class_id)] = nav_per_share
                            targets_by_id[int(share_class_id)] = {
                                "total_shares": total_shares,
                                "total_nav": total_nav,
                            }
                        if class_code:
                            code_key = str(class_code).strip()
                            breakdown_by_code[code_key] = nav_per_share
                            targets_by_code[code_key] = {
                                "total_shares": total_shares,
                                "total_nav": total_nav,
                            }
            except Exception:
                breakdown_by_id = {}
                breakdown_by_code = {}
                targets_by_id = {}
                targets_by_code = {}

        use_breakdown = bool(breakdown_by_id or breakdown_by_code)
        if not use_breakdown and (batch.deployment_nav is None or batch.deployment_nav <= 0):
            return

        computed_totals = {}
        for inv in investments:
            inv_net = Decimal(str(inv.net_principal or 0))
            if inv_net <= 0:
                inv.shares_owned = Decimal('0')
                inv.opening_market_value = Decimal('0')
                inv.previous_nav_price = batch.deployment_nav
                inv.date_transferred = batch.date_deployed
                session.add(inv)
                continue

            share_class_id = inv.share_class_id if inv.share_class_id is not None else batch.share_class_id
            nav_per_share = None
            if use_breakdown:
                if share_class_id is not None and share_class_id in breakdown_by_id:
                    nav_per_share = breakdown_by_id[share_class_id]
                elif inv.share_class and inv.share_class.class_code in breakdown_by_code:
                    nav_per_share = breakdown_by_code[inv.share_class.class_code]
                elif batch.share_class and batch.share_class.class_code in breakdown_by_code:
                    nav_per_share = breakdown_by_code[batch.share_class.class_code]
            if nav_per_share is None:
                nav_per_share = batch.deployment_nav

            if nav_per_share is None or nav_per_share <= 0:
                continue

            shares = (inv_net / nav_per_share).quantize(Decimal('0.0001'))
            inv.shares_owned = shares
            inv.previous_nav_price = nav_per_share
            inv.date_transferred = batch.date_deployed
            inv.opening_market_value = (shares * nav_per_share).quantize(Decimal('0.01'))
            if inv.share_class_id is None and batch.share_class_id:
                inv.share_class_id = batch.share_class_id
            session.add(inv)

            class_key = share_class_id if share_class_id is not None else (inv.share_class.class_code if inv.share_class else None)
            if class_key is None:
                class_key = f"unknown-{inv.id}"

            if class_key not in computed_totals:
                computed_totals[class_key] = {
                    "shares": Decimal('0'),
                    "nav": Decimal('0'),
                    "nav_per_share": nav_per_share,
                    "investments": [],
                }

            computed_totals[class_key]["shares"] += shares
            computed_totals[class_key]["nav"] += inv.opening_market_value
            computed_totals[class_key]["investments"].append(inv)

        for class_key, bucket in computed_totals.items():
            target = None
            if isinstance(class_key, int) and class_key in targets_by_id:
                target = targets_by_id[class_key]
            elif isinstance(class_key, str) and class_key in targets_by_code:
                target = targets_by_code[class_key]
            if target and target["total_shares"] > 0 and bucket["shares"] > 0:
                shares_diff = abs(bucket["shares"] - target["total_shares"])
                if shares_diff >= Decimal('0.01'):
                    ratio = target["total_shares"] / bucket["shares"]
                    adjusted_shares = Decimal('0')
                    adjusted_nav = Decimal('0')
                    for inv in bucket["investments"]:
                        inv.shares_owned = (Decimal(str(inv.shares_owned or 0)) * ratio).quantize(Decimal('0.0001'))
                        inv.opening_market_value = (inv.shares_owned * bucket["nav_per_share"]).quantize(Decimal('0.01'))
                        session.add(inv)
                        adjusted_shares += inv.shares_owned
                        adjusted_nav += inv.opening_market_value
                    bucket["shares"] = adjusted_shares
                    bucket["nav"] = adjusted_nav

        batch.total_shares = sum((bucket["shares"] for bucket in computed_totals.values()), Decimal('0'))
        if use_breakdown:
            # Use computed class NAV totals to avoid double-counting when both
            # share_class_id and class_code reference the same class.
            batch.deployment_total_nav = sum((bucket["nav"] for bucket in computed_totals.values()), Decimal('0'))
        else:
            batch.deployment_total_nav = (batch.total_shares * batch.deployment_nav).quantize(Decimal('0.01'))
        session.add(batch)

        # Prefetch every existing InvestorShares row for this batch in ONE query
        # instead of one .first() lookup per investment — at 100k investments
        # that was 100,000 round trips just to decide insert-vs-update, on top
        # of everything else this method already does.
        existing_shares_by_key = {
            (s.investment_id, s.share_class_id): s
            for s in session.query(InvestorShares).filter(InvestorShares.batch_id == batch.id).all()
        }
        new_share_rows = []
        for inv in investments:
            if inv.shares_owned is None:
                continue
            share_class_id = inv.share_class_id
            investor_share = existing_shares_by_key.get((inv.id, share_class_id))
            if investor_share:
                investor_share.shares_owned = inv.shares_owned
                investor_share.deployment_nav = inv.previous_nav_price
                investor_share.deployment_date = deployment_date
                investor_share.is_active = True
                session.add(investor_share)
            else:
                new_share_rows.append({
                    "investment_id": inv.id,
                    "share_class_id": share_class_id,
                    "batch_id": batch.id,
                    "shares_owned": inv.shares_owned,
                    "deployment_nav": inv.previous_nav_price,
                    "deployment_date": deployment_date,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                })

        if new_share_rows:
            session.execute(insert(InvestorShares), new_share_rows)

    @classmethod
    def deploy_batch(cls, batch_id, data, session):
        """
        Officially deploy a batch using a specific NAV per share and date.
        Performs reconciliation and pro-rata fee deduction.
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

            # 1. Extract and validate inputs
            deployment_date_str = data.get('deployment_date')
            nav_per_share = Decimal(str(data.get('nav_per_share', 0)))
            total_nav = Decimal(str(data.get('total_nav', 0)))
            total_shares_input = Decimal(str(data.get('total_shares', 0)))
            transfer_cost = Decimal(str(data.get('transfer_cost', 0)))
            entry_fee_pct = Decimal(str(data.get('entry_fee_pct', 0)))

            if not deployment_date_str or nav_per_share <= 0:
                return make_response(jsonify({"status": 400, "message": "Deployment date and NAV per share (>0) are required"}), 400)

            # 2. Reconciliation Check (within $1.00)
            calculated_nav = (total_shares_input * nav_per_share).quantize(Decimal("0.01"))
            discrepancy = abs(calculated_nav - total_nav)
            if discrepancy >= 1.00:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Reconciliation failed. Calculated NAV (${calculated_nav:,.2f}) differs from AXYS Total NAV (${total_nav:,.2f}) by ${discrepancy:,.2f}. Must be < $1.00."
                }), 400)

            # 3. Apply Pro-rata Deductions & Calculations
            investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
            total_deposited = sum(Decimal(str(inv.amount_deposited)) for inv in investments)
            
            if total_deposited <= 0:
                 return make_response(jsonify({"status": 400, "message": "Batch has no deposits to deploy"}), 400)

            deployment_dt = datetime.fromisoformat(deployment_date_str)
            if deployment_dt.tzinfo is None:
                deployment_dt = deployment_dt.replace(tzinfo=timezone.utc)

            for inv in investments:
                original_principal = Decimal(str(inv.amount_deposited))
                # Share of transfer cost = (Inv Principal / Total Principal) * Total Transfer Cost
                inv_transfer_fee = (original_principal / total_deposited * transfer_cost).quantize(Decimal("0.01"))
                # Entry Fee % deduction
                inv_entry_fee = (original_principal * (entry_fee_pct / 100)).quantize(Decimal("0.01"))
                
                inv.transfer_fee_deducted = inv_transfer_fee
                inv.deployment_fee_deducted = inv_entry_fee
                inv.net_principal = original_principal - inv_transfer_fee - inv_entry_fee
                
                # Assign shares
                inv.share_series = inv.fund.fund_name if inv.fund else inv.fund_name
                inv.shares_owned = (inv.net_principal / nav_per_share).quantize(Decimal("0.0001"))
                inv.date_transferred = deployment_dt
            
            # 4. Update Batch record
            batch.date_deployed = deployment_dt
            batch.deployment_date_actual = deployment_dt.date()
            batch.deployment_nav = nav_per_share
            batch.total_shares = total_shares_input
            batch.deployment_total_nav = total_nav
            batch.transfer_transaction_cost = transfer_cost
            batch.transaction_cost = sum(Decimal(str(inv.deployment_fee_deducted)) for inv in investments)
            batch.deployment_confirmed = True
            batch.is_active = True
            batch.is_transferred = True
            batch.stage = 4 # Portfolio Active

            session.commit()

            # 5. Audit Log & Email
            create_audit_log(
                action='BATCH_DEPLOYED',
                target_type='batch',
                target_id=batch.id,
                target_name=batch.batch_name,
                description=f'Batch deployed at NAV {nav_per_share} on {deployment_date_str}',
                new_value={
                    "nav_per_share": float(nav_per_share),
                    "total_nav": float(total_nav),
                    "total_shares": float(total_shares_input),
                    "transfer_cost": float(transfer_cost)
                },
                success=True
            )
            
            EmailService.send_investment_active_batch(batch, trigger_source="batch.controller.deploy_endpoint")

            return make_response(jsonify({
                "status": 200,
                "message": "Batch deployed and activated successfully",
                "data": {
                    "batch_id": batch.id,
                    "total_shares": float(batch.total_shares),
                    "nav_per_share": float(batch.deployment_nav),
                    "total_nav": float(batch.deployment_total_nav or 0),
                }
            }), 200)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({"status": 500, "message": f"Deployment error: {str(e)}"}), 500)

    @classmethod
    def _calculate_batch_investment_values(
        cls, inv, batch, session, wd_prefetch: dict = None,
        shares_prefetch: dict = None, snapshot_prefetch: dict = None, nav_price_cache: dict = None,
        wd_detail_prefetch: dict = None,
    ):
        """
        Per-investment values scoped strictly to this batch.

        Priority: latest committed Statement snapshot for this specific batch
        → fallback to net principal minus batch-scoped withdrawals.

        Optional bulk-context args — pass these when calling this in a loop over
        many investments in the SAME deployed batch so each call skips its own
        per-row queries (this is what made refresh_cached_total_capital take
        minutes on a 100k-investment deployed batch: 3-4 queries per row with
        none of this):
          wd_prefetch: {(client_code, fund_id): Decimal} from
            _prefetch_withdrawal_sums_for_batch.
          shares_prefetch: {investment_id: InvestorShares} — one query's worth
            of every InvestorShares row for the batch, from
            _prefetch_investor_shares_for_batch.
          snapshot_prefetch: {investor_shares_id: latest ValuationSnapshot} from
            _prefetch_latest_valuation_snapshots.
          nav_price_cache: a plain {} the caller creates once and passes through
            every call in the loop — memoizes NavHistory.resolve_current_price
            by (share_class_id, deployment_date, deployment_nav), which is a
            pure function of those inputs and, within one batch, usually has
            only a handful of distinct keys across thousands of investments.
        Any of these left as None falls back to that tier's own per-row query,
        so single-investment callers (Investor Overview, etc.) are unaffected.
        """
        opening_balance = float(inv.net_principal)
        if batch is None or batch.date_deployed is None:
            wd = cls._withdrawals_for_investment_batch(session, inv, batch.id if batch else None, wd_prefetch=wd_prefetch)
            return {
                "opening_balance": opening_balance,
                "current_balance": max(0.0, float(Decimal(str(opening_balance)) - wd)),
                "profit": 0.0,
                "withdrawals": float(wd),
            }

        wd = cls._withdrawals_for_investment_batch(session, inv, batch.id, wd_prefetch=wd_prefetch)
        share_series = inv.share_series or (inv.fund.fund_name if inv.fund else inv.fund_name)
        shares_owned = Decimal(str(inv.shares_owned or 0))

        # SSOT: Committed epoch valuation statements are per investment + batch.
        st = (
            session.query(Statement)
            .join(ValuationRun, Statement.valuation_run_id == ValuationRun.id)
            .filter(
                Statement.investor_id == inv.id,
                Statement.batch_id == batch.id,
                func.lower(ValuationRun.status) == "committed",
            )
            .order_by(ValuationRun.epoch_end.desc())
            .first()
        )

        if st:
            base_cb = Decimal(str(st.closing_balance))
            uncaptured_wd = cls._uncaptured_withdrawals_for_investment_batch(
                session, inv, batch.id, st.date_issued, wd_detail_prefetch=wd_detail_prefetch
            )
            cb = max(Decimal("0"), _q2(base_cb - uncaptured_wd))
            profit = _q2(cb - Decimal(str(opening_balance)))
            return {
                "opening_balance": opening_balance,
                "current_balance": float(cb),
                "profit": float(profit),
                "withdrawals": float(wd),
            }

        # SSOT for Share-Based NAV Model: ValuationSnapshot via InvestorShares
        try:
            from app.Funds.investor_shares import InvestorShares
            from app.Valuation.valuation_snapshot import ValuationSnapshot
            from app.Funds.nav_history import NavHistory

            if shares_prefetch is not None:
                inv_shares = shares_prefetch.get(inv.id)
            else:
                inv_shares = session.query(InvestorShares).filter(
                    InvestorShares.investment_id == inv.id
                ).first()

            if inv_shares:
                if snapshot_prefetch is not None:
                    latest_snap = snapshot_prefetch.get(inv_shares.id)
                else:
                    latest_snap = (
                        session.query(ValuationSnapshot)
                        .filter(ValuationSnapshot.investor_shares_id == inv_shares.id)
                        .order_by(ValuationSnapshot.valuation_date.desc())
                        .first()
                    )
                if latest_snap and latest_snap.market_value is not None:
                    base_cb = Decimal(str(latest_snap.market_value))
                    uncaptured_wd = cls._uncaptured_withdrawals_for_investment_batch(
                        session, inv, batch.id, latest_snap.valuation_date, wd_detail_prefetch=wd_detail_prefetch
                    )
                    cb = max(Decimal("0"), _q2(base_cb - uncaptured_wd))
                    profit = _q2(cb - Decimal(str(opening_balance)))
                    dep_nav = Decimal(str(inv_shares.deployment_nav or inv.previous_nav_price or 1))
                    curr_nav = Decimal(str(latest_snap.nav_per_share or 0))
                    shs = Decimal(str(latest_snap.shares_held or inv_shares.shares_owned or 0))
                    perf_pct = Decimal(str(latest_snap.performance_pct or 0))
                    return {
                        "opening_balance": opening_balance,
                        "current_balance": float(cb),
                        "profit": float(profit),
                        "withdrawals": float(wd),
                        "performance_pct": float(perf_pct),
                        "current_nav": float(curr_nav),
                        "purchase_nav": float(dep_nav),
                        "shares_owned": float(shs),
                    }

                # If no snapshot yet, calculate from NavHistory — resolve_current_price
                # is the single source of truth for "current price" (see its docstring):
                # a NavHistory row dated on/after THIS deployment, never an older one
                # left over from a different deployment or stale seed/test data.
                sc_id = inv_shares.share_class_id or inv.share_class_id or (batch.share_class_id if batch else None)
                shs = Decimal(str(inv_shares.shares_owned or inv.shares_owned or 0))
                dep_nav = Decimal(str(inv_shares.deployment_nav or inv.previous_nav_price or 1))
                if sc_id and shs > Decimal("0"):
                    nav_cache_key = (sc_id, inv_shares.deployment_date, dep_nav)
                    if nav_price_cache is not None and nav_cache_key in nav_price_cache:
                        curr_nav, nav_date, _is_fallback = nav_price_cache[nav_cache_key]
                    else:
                        curr_nav, nav_date, _is_fallback = NavHistory.resolve_current_price(
                            sc_id, inv_shares.deployment_date, dep_nav, session=session
                        )
                        if nav_price_cache is not None:
                            nav_price_cache[nav_cache_key] = (curr_nav, nav_date, _is_fallback)
                    if curr_nav is not None:
                        base_cb = _q2(shs * curr_nav)
                        uncaptured_wd = cls._uncaptured_withdrawals_for_investment_batch(
                            session, inv, batch.id, nav_date, wd_detail_prefetch=wd_detail_prefetch
                        )
                        cb = max(Decimal("0"), _q2(base_cb - uncaptured_wd))
                        profit = _q2(cb - Decimal(str(opening_balance)))
                        perf_pct = ((curr_nav / dep_nav) - Decimal("1")) * Decimal("100") if dep_nav > 0 else Decimal("0")
                        return {
                            "opening_balance": opening_balance,
                            "current_balance": float(cb),
                            "profit": float(profit),
                            "withdrawals": float(wd),
                            "performance_pct": float(_q2(perf_pct)),
                            "current_nav": float(curr_nav),
                            "purchase_nav": float(dep_nav),
                            "shares_owned": float(shs),
                        }
        except Exception:
            pass

        if share_series and shares_owned > Decimal("0"):
            purchase_nav_row = cls._latest_nav_for_series(session, share_series, batch.date_deployed)
            current_nav_row = cls._latest_nav_for_series(session, share_series, None)
            if purchase_nav_row and current_nav_row:
                purchase_nav = Decimal(str(purchase_nav_row.nav_price or 0))
                current_nav = Decimal(str(current_nav_row.nav_price or 0))
                if purchase_nav > 0 and current_nav > 0:
                    nav_balance = _q2(shares_owned * current_nav)
                    cb = max(Decimal("0"), _q2(nav_balance - wd))
                    profit = _q2((shares_owned * current_nav) - (shares_owned * purchase_nav))
                    perf_pct = ((current_nav / purchase_nav) - Decimal("1")) * Decimal("100")
                    return {
                        "opening_balance": opening_balance,
                        "current_balance": float(cb),
                        "profit": float(profit),
                        "withdrawals": float(wd),
                        "performance_pct": float(_q2(perf_pct)),
                        "current_nav": float(current_nav),
                        "purchase_nav": float(purchase_nav),
                        "shares_owned": float(shares_owned),
                    }

        # BatchValuation fallback:
        # If Statement rows are missing (can happen during backfills/preview paths),
        # use the committed per-investment batch valuation snapshots instead of
        # falling back to epoch-ledger attribution, which may be investor/fund-scoped.
        latest_inv_bv = (
            session.query(InvestmentBatchValuation)
            .filter(
                InvestmentBatchValuation.investment_id == inv.id,
                InvestmentBatchValuation.batch_id == batch.id,
            )
            .order_by(InvestmentBatchValuation.period_end_date.desc())
            .first()
        )
        if latest_inv_bv is not None:
            cb = _q2(Decimal(str(latest_inv_bv.balance_at_end_of_period or 0)))
            profit = _q2(cb - Decimal(str(opening_balance)))
            return {
                "opening_balance": opening_balance,
                "current_balance": float(max(Decimal("0"), cb)),
                "profit": float(profit),
                "withdrawals": float(wd),
            }

        eb, eb_epoch_end = cls._epoch_ledger_attributed_balance_and_epoch_end(inv, session)
        if eb is not None and eb_epoch_end is not None:
            uncaptured_wd = cls._uncaptured_withdrawals_for_investment_batch(
                session, inv, batch.id, eb_epoch_end, wd_detail_prefetch=wd_detail_prefetch
            )
            cb = max(Decimal("0"), _q2(eb - uncaptured_wd))
            profit = _q2(cb - Decimal(str(opening_balance)))
            return {
                "opening_balance": opening_balance,
                "current_balance": float(cb),
                "profit": float(profit),
                "withdrawals": float(wd),
            }

        # Fallback: No statement or epoch ledger exists, just net principal minus withdrawals
        cb = _q2(Decimal(str(opening_balance)) - wd)
        cb_f = max(Decimal("0"), cb)
        return {
            "opening_balance": opening_balance,
            "current_balance": float(cb_f),
            "profit": 0.0,
            "withdrawals": float(wd),
        }

    @classmethod
    def _prefetch_valuation_cascade(cls, session, investments) -> dict:
        """
        One shot at prefetching everything _calculate_batch_investment_values'
        per-row queries need, for a whole batch's worth of investments at once.
        Returns kwargs ready to ** into _calculate_batch_investment_values calls.
        Safe (if wasteful) to call for a not-yet-deployed batch too — shares/
        snapshot prefetches just come back empty and every row takes the early
        "not deployed" return before touching them.
        """
        wd_prefetch = cls._prefetch_withdrawal_sums_for_batch(session, investments)
        wd_detail_prefetch = cls._prefetch_withdrawal_details_for_batch(session, investments)
        shares_prefetch = cls._prefetch_investor_shares_for_batch(session, investments)
        snapshot_prefetch = cls._prefetch_latest_valuation_snapshots(
            session, [s.id for s in shares_prefetch.values()]
        )
        return {
            "wd_prefetch": wd_prefetch,
            "wd_detail_prefetch": wd_detail_prefetch,
            "shares_prefetch": shares_prefetch,
            "snapshot_prefetch": snapshot_prefetch,
            "nav_price_cache": {},
        }

    @classmethod
    def _calculate_batch_current_standing(cls, batch, session):
        """Calculate total current standing for a batch using per-investment batch valuation."""
        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        total_current_standing = Decimal("0")

        # One shot at prefetching every per-row query _calculate_batch_investment_values
        # would otherwise make (withdrawals, InvestorShares, ValuationSnapshot, NavHistory)
        # instead of paying for them once per investment — see _prefetch_valuation_cascade.
        prefetch = cls._prefetch_valuation_cascade(session, investments)

        for inv in investments:
            values = cls._calculate_batch_investment_values(inv, batch, session, **prefetch)
            total_current_standing += Decimal(str(values.get("current_balance", 0)))

        return float(round(total_current_standing, 2))

    @classmethod
    def refresh_cached_total_capital(cls, batch, session, commit=True):
        """
        Recomputes this batch's total current standing (same math as
        _calculate_batch_current_standing — the per-investment valuation cascade in
        _calculate_batch_investment_values) and stores it on the batch row, so read
        paths (get_batch_by_id, get_all_batches) can use the stored number instead of
        recomputing on every page load.

        Call this after anything that changes what _calculate_batch_investment_values
        would return for this batch's investments: batch deployment, a withdrawal
        being approved/rejected, a valuation run being committed, or a manual edit to
        an investment's shares/NAV. See callers for the full list of write sites.

        Accepts a Batch instance or a batch_id; returns the new cached total as a float,
        or None if the batch doesn't exist.
        """
        if not isinstance(batch, Batch):
            batch = session.query(Batch).filter(Batch.id == batch).first()
        if batch is None:
            return None

        investments = session.query(Investment).filter(Investment.batch_id == batch.id).all()
        prefetch = cls._prefetch_valuation_cascade(session, investments)
        total = Decimal("0.00")
        for inv in investments:
            try:
                values = cls._calculate_batch_investment_values(inv, batch, session, **prefetch)
                total += Decimal(str(values.get("current_balance", 0)))
            except Exception:
                # Same fallback used everywhere else this calculation is attempted.
                total += Decimal(str(inv.net_principal or 0))

        batch.cached_total_capital = total.quantize(Decimal("0.01"))
        batch.cached_total_capital_at = datetime.now(timezone.utc)
        session.add(batch)
        if commit:
            session.commit()
        return float(batch.cached_total_capital)

    @classmethod
    def refresh_cached_total_capital_for_batch_ids(cls, batch_ids, session, commit=True):
        """Bulk variant of refresh_cached_total_capital for write paths that can touch
        more than one batch at once (valuation commit, withdrawal approval, bulk Excel
        import). Commits once at the end rather than once per batch."""
        unique_ids = {bid for bid in batch_ids if bid is not None}
        results = {}
        for bid in unique_ids:
            results[bid] = cls.refresh_cached_total_capital(bid, session, commit=False)
        if commit and unique_ids:
            session.commit()
        return results

    @classmethod
    def get_all_batches(cls, session, product=None):
        """
        Get all batches with calculated fields.

        Args:
            session: database session
            product: optional 'FUNDS' or 'SHARES' filter (see app.database.product_type).
                     Omitted/None keeps today's default behaviour (all products).

        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batches_query = session.query(Batch)
            if product:
                batches_query = batches_query.filter(Batch.product_type == product)
            batches = batches_query.all()
            
            batch_list = []
            for batch in batches:
                # Base principal (deposits)
                total_deposits_sum = session.query(db.func.sum(Investment.amount_deposited)).filter(
                    Investment.batch_id == batch.id
                ).scalar() or 0.00

                # Prefer persisted batch valuation, but only from committed valuation runs.
                # BatchValuation rows can be written during dry-runs/uncommitted previews,
                # which must not affect "Before <next> Valuations" dashboards.
                latest_bv = (
                    session.query(BatchValuation)
                    .join(
                        ValuationRun,
                        BatchValuation.period_end_date == ValuationRun.epoch_end,
                    )
                    .filter(
                        BatchValuation.batch_id == batch.id,
                        func.lower(ValuationRun.status) == "committed",
                    )
                    .order_by(BatchValuation.period_end_date.desc())
                    .first()
                )
                if latest_bv:
                    total_value = float(latest_bv.balance_at_end_of_period or 0)
                elif batch.cached_total_capital is not None:
                    total_value = float(batch.cached_total_capital)
                else:
                    # Live fallback + self-heal: older batches or ones that predate this cache.
                    total_value = cls.refresh_cached_total_capital(batch, session)

                # Count unique investors (by distinct internal_client_code)
                investors_count = session.query(
                    db.func.count(distinct(Investment.internal_client_code))
                ).filter(
                    Investment.batch_id == batch.id
                ).scalar() or 0

                # Hide empty batches from the list.
                if int(investors_count) == 0:
                    continue
                
                # ── Resolve canonical deployment date ──
                effective_date = batch.date_deployed
                active_days = cls._calculate_active_days(batch)
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
                    "active_days": active_days,
                    "expected_close_date": (effective_date + timedelta(days=batch.duration_days)).isoformat() if effective_date else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "transaction_cost": float(batch.transaction_cost or 0),
                    "transfer_transaction_cost": float(batch.transfer_transaction_cost or 0),
                    "investors_count": investors_count,
                    "is_active": batch.is_active,
                    "status": status,
                    "stage": calculated_stage,
                    "share_class_id": batch.share_class_id,
                    "class_code": batch.share_class.class_code if batch.share_class is not None else None,
                    "class_currency": batch.share_class.currency if batch.share_class is not None else None,
                    "deployment_total_nav": float(batch.deployment_total_nav) if getattr(batch, "deployment_total_nav", None) is not None else None,
                    "product_type": batch.product_type,
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
    def get_batches_summary_counts(cls, session):
        """
        Return batch counts matching the batches page directory.

        Investor counts per batch are computed in a single GROUP BY instead of
        one COUNT(DISTINCT ...) query per batch — this used to be an N+1 that
        scaled with the number of batches (called from the Overview page on
        every load).
        """
        try:
            investor_counts = dict(
                session.query(
                    Investment.batch_id,
                    db.func.count(distinct(Investment.internal_client_code)),
                ).group_by(Investment.batch_id).all()
            )

            batches = session.query(Batch).all()
            open_count = 0
            active_count = 0
            total_count = 0

            for batch in batches:
                if int(investor_counts.get(batch.id, 0) or 0) == 0:
                    continue

                total_count += 1
                if getattr(batch, "is_open", True) and not getattr(batch, "date_closed", None):
                    open_count += 1
                if getattr(batch, "is_active", False):
                    active_count += 1

            display_open = open_count if open_count > 0 else (active_count if active_count > 0 else total_count)
            display_active = active_count if active_count > 0 else total_count

            return {
                "total_batches": total_count,
                "open_batches": display_open,
                "active_batches": display_active,
            }
        except Exception:
            return {
                "total_batches": 0,
                "open_batches": 0,
                "active_batches": 0,
            }

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
            transfer_entry_fee_percent = Decimal("0")
            transfer_settings_changed = False

            # SHARES deployment validation MUST happen before any field below is
            # mutated (same reasoning as the transfer-fee check below it) — a 400
            # here is guaranteed to mean zero mutation, no matter what else is in
            # `data`. Replaces the old flat-rate DPRP oversubscription validation
            # (is_oversubscribed/allocation_rate) with Task 3's NGN-based allocation.
            incoming_date_deployed = data.get('date_deployed') or batch.date_deployed
            if (
                batch.product_type == SHARES
                and 'deployment_confirmed' in data and data.get('deployment_confirmed')
                and not old_deployment_confirmed and incoming_date_deployed is not None
            ):
                investments_for_deploy_check = session.query(Investment).filter(Investment.batch_id == batch.id).all()
                try:
                    SharesDeploymentService.validate_inputs(
                        investments_for_deploy_check,
                        data.get('exchange_rate'),
                        data.get('price_per_share_ngn'),
                        data.get('shares_allocated'),
                    )
                except SharesDeploymentError as e:
                    return make_response(jsonify({"status": 400, "message": str(e)}), 400)

            # SHARES transfer-fee validation — same reasoning as the deployment
            # check above: must happen before any field below is mutated, so a 400
            # here is guaranteed to mean zero mutation. Only applies when this request
            # is the one flipping is_transferred False -> True for a SHARES batch;
            # FUNDS keeps its existing (unvalidated) transfer-stage behaviour.
            if (
                batch.product_type == SHARES
                and 'is_transferred' in data and data.get('is_transferred')
                and not old_is_transferred
            ):
                entry_fee_percent_check = Decimal(str(
                    data.get('entry_fee_percentage', data.get('transfer_entry_fee_percent', 0)) or 0
                ))
                total_cost_check = Decimal(str(
                    data.get('transfer_transaction_cost', batch.transfer_transaction_cost or 0)
                ))
                investments_check = session.query(Investment).filter(Investment.batch_id == batch.id).all()
                try:
                    SharesTransferService.validate_inputs(investments_check, entry_fee_percent_check, total_cost_check)
                except SharesTransferError as e:
                    return make_response(jsonify({"status": 400, "message": str(e)}), 400)

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
                    batch.date_deployed = datetime.fromisoformat(str(data['date_deployed']).replace("Z", "+00:00"))
                else:
                    batch.date_deployed = None
            if 'deployment_date_actual' in data:
                if data['deployment_date_actual'] is not None:
                    batch.deployment_date_actual = datetime.fromisoformat(str(data['deployment_date_actual']).replace("Z", "+00:00")).date()
                else:
                    batch.deployment_date_actual = None
            if 'deployment_nav' in data:
                batch.deployment_nav = Decimal(str(data['deployment_nav'])) if data['deployment_nav'] is not None else None
            if 'total_shares' in data:
                batch.total_shares = Decimal(str(data['total_shares'])) if data['total_shares'] is not None else None
            if 'total_nav' in data:
                batch.deployment_total_nav = Decimal(str(data['total_nav'])) if data['total_nav'] is not None else None
            if 'deployment_breakdown' in data:
                batch.deployment_breakdown = json.dumps(data['deployment_breakdown']) if data['deployment_breakdown'] is not None else None
            if 'transfer_transaction_cost' in data:
                batch.transfer_transaction_cost = Decimal(str(data['transfer_transaction_cost']))
                transfer_settings_changed = True
            if 'entry_fee_percentage' in data:
                transfer_entry_fee_percent = Decimal(str(data['entry_fee_percentage']))
                transfer_settings_changed = True
            elif 'transfer_entry_fee_percent' in data:
                transfer_entry_fee_percent = Decimal(str(data['transfer_entry_fee_percent']))
                transfer_settings_changed = True
            if transfer_entry_fee_percent < 0:
                return make_response(jsonify({
                    "status": 400,
                    "message": "Entry fee percentage cannot be negative"
                }), 400)
            if 'is_active' in data:
                batch.is_active = data['is_active']
            if 'is_transferred' in data:
                batch.is_transferred = data['is_transferred']
            if 'deployment_confirmed' in data:
                batch.deployment_confirmed = data['deployment_confirmed']

            session.commit()

            # Send emails based on stage changes
            try:
                # If a batch is already transferred and the transfer settings are edited later,
                # we must recompute per-investor deductions so the UI and statements reflect
                # the latest rules (transaction cost + entry fee on gross deposit).
                # This MUST NOT retrigger investor emails.
                # FUNDS only — SHARES fees are locked once Transferred (see Task 2):
                # recomputing here would silently violate that lock.
                if (
                    batch.product_type != SHARES
                    and batch.is_transferred and transfer_settings_changed
                    and not ('is_transferred' in data and data.get('is_transferred') and not old_is_transferred)
                ):
                    try:
                        deduction_summary = StatusUpdateController._apply_transfer_cost_deduction(
                            batch,
                            session,
                            transfer_cost_total=batch.transfer_transaction_cost,
                            entry_fee_percent=transfer_entry_fee_percent,
                        )
                        batch.transfer_transaction_cost = Decimal(str(deduction_summary["total_transaction_fee_usd"]))
                        session.commit()
                    except Exception as recompute_err:
                        logger.warning(f"Failed to recompute transfer deductions for batch {batch.id}: {recompute_err}")

                # Admin "moved back" a SHARES batch (is_transferred True -> False):
                # unlock and clear the per-investment fee fields, audited with old/new
                # values — the next Transferred run recalculates from scratch.
                if (
                    batch.product_type == SHARES
                    and 'is_transferred' in data and not data.get('is_transferred') and old_is_transferred
                ):
                    old_totals, new_totals = SharesTransferService.revert_lock(batch, session)
                    create_audit_log(
                        action='SHARES_TRANSFER_REVERTED',
                        target_type='batch',
                        target_id=batch.id,
                        target_name=batch.batch_name,
                        description=f'Batch "{batch.batch_name}" moved back from Transferred — SHARES transfer fees unlocked and cleared.',
                        old_value=old_totals,
                        new_value=new_totals,
                        success=True
                    )

                # Stage 2: When is_transferred changes to True
                if 'is_transferred' in data and data['is_transferred'] and not old_is_transferred:
                    if batch.product_type == SHARES:
                        totals = SharesTransferService.apply_to_batch(
                            batch,
                            session,
                            entry_fee_percent=transfer_entry_fee_percent,
                            total_transaction_cost_usd=batch.transfer_transaction_cost,
                        )
                        batch.transfer_transaction_cost = totals["transaction_cost_usd"]
                    else:
                        deduction_summary = StatusUpdateController._apply_transfer_cost_deduction(
                            batch,
                            session,
                            transfer_cost_total=batch.transfer_transaction_cost,
                            entry_fee_percent=transfer_entry_fee_percent,
                        )
                        batch.transfer_transaction_cost = Decimal(str(deduction_summary["total_transaction_fee_usd"]))
                    session.commit()
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
                    cls._on_batch_transferred(batch, session)

                # Admin "moved back" a SHARES batch (deployment_confirmed True -> False):
                # unlock, clear the per-investment allocation fields, and reject any
                # still-Pending refund Withdrawals — audited with old/new values.
                if (
                    batch.product_type == SHARES
                    and 'deployment_confirmed' in data and not data.get('deployment_confirmed')
                    and old_deployment_confirmed
                ):
                    old_values, new_values = SharesDeploymentService.revert_lock(batch, session)
                    create_audit_log(
                        action='SHARES_DEPLOYMENT_REVERTED',
                        target_type='batch',
                        target_id=batch.id,
                        target_name=batch.batch_name,
                        description=f'Batch "{batch.batch_name}" moved back from Deployed — SHARES allocation unlocked and cleared.',
                        old_value=old_values,
                        new_value=new_values,
                        success=True
                    )

                # Stage 3: When deployment_confirmed changes to True and date_deployed is set
                if ('deployment_confirmed' in data and data['deployment_confirmed'] and
                    not old_deployment_confirmed and batch.date_deployed is not None):
                    batch.is_active = True

                    if batch.product_type == SHARES:
                        # Validated up-front (before any field on this batch was touched),
                        # so by this point it's known-good. Replaces the old flat-rate DPRP
                        # oversubscription allocation with Task 3's NGN-based allocation —
                        # ONE implementation, run unconditionally (not just "if
                        # oversubscribed"): even a fully-subscribed batch can have small
                        # per-investor refunds from floor-rounding leftover shares.
                        deployment_summary = SharesDeploymentService.apply_to_batch(
                            batch, session,
                            exchange_rate=data.get('exchange_rate'),
                            price_per_share_ngn=data.get('price_per_share_ngn'),
                            shares_allocated=data.get('shares_allocated'),
                        )
                        session.commit()
                        cls.refresh_cached_total_capital(batch, session)

                        refunded_investor_ids = deployment_summary.get("_refunded_investor_ids") or []
                        if refunded_investor_ids:
                            EmailService.send_investment_active_batch(
                                batch, trigger_source="batch.patch.stage_3_deploy_shares",
                            )
                            EmailService.send_oversubscription_refund_notices(
                                batch, refunded_investor_ids,
                                trigger_source="batch.patch.stage_3_deploy_shares",
                            )
                            create_audit_log(
                                action='SHARES_DEPLOYMENT_ALLOCATION',
                                target_type='batch',
                                target_id=batch.id,
                                target_name=batch.batch_name,
                                description=(
                                    f'Batch "{batch.batch_name}" deployed — '
                                    f'{"Oversubscribed" if deployment_summary["is_oversubscribed"] else "Fully subscribed"}, '
                                    f'{len(refunded_investor_ids)} investor(s) refunded.'
                                ),
                                new_value={k: v for k, v in deployment_summary.items() if not k.startswith("_")},
                                success=True
                            )
                        else:
                            EmailService.send_investment_active_batch(batch, trigger_source="batch.patch.stage_3_deploy_shares")
                    else:
                        cls._deploy_shares_for_batch(batch, session)
                        session.commit()
                        cls.refresh_cached_total_capital(batch, session)
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
                    cls._on_batch_deployed(batch, session)

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
                    "deployment_date_actual": batch.deployment_date_actual.isoformat() if getattr(batch, "deployment_date_actual", None) else None,
                    "deployment_nav": float(batch.deployment_nav) if getattr(batch, "deployment_nav", None) is not None else None,
                    "total_shares": float(batch.total_shares) if getattr(batch, "total_shares", None) is not None else None,
                    "deployment_total_nav": float(batch.deployment_total_nav) if getattr(batch, "deployment_total_nav", None) is not None else None,
                    "deployment_breakdown": json.loads(batch.deployment_breakdown) if getattr(batch, "deployment_breakdown", None) else None,
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
            from app.Reports.model import ReportRecipient, ReportRun
            from app.Batch.fund import Fund, FundPerformance
            from app.Valuation.model import Statement, BatchValuation, InvestmentBatchValuation
            from app.Funds.investor_shares import InvestorShares
            from app.Performance.model import Performance
            from app.Performance.pro_rata_distribution import ProRataDistribution

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
                # Valuation statements for this batch
                session.query(Statement).filter(Statement.batch_id == batch_id).delete(synchronize_session=False)
                # report_recipients.investor_id FK points to investments.id. Must be removed first.
                touched_run_ids = [
                    rid for (rid,) in session.query(ReportRecipient.report_run_id)
                    .filter(ReportRecipient.investor_id.in_(investment_ids))
                    .distinct()
                    .all()
                ]
                session.query(ReportRecipient).filter(
                    ReportRecipient.investor_id.in_(investment_ids)
                ).delete(synchronize_session=False)

                # Cleanup orphan report runs with zero recipients to keep history clean.
                if touched_run_ids:
                    for run_id in touched_run_ids:
                        remaining = session.query(ReportRecipient.id).filter(
                            ReportRecipient.report_run_id == run_id
                        ).first()
                        if not remaining:
                            session.query(ReportRun).filter(ReportRun.id == run_id).delete(synchronize_session=False)

            # Batch-scoped valuation artifacts
            session.query(InvestmentBatchValuation).filter(InvestmentBatchValuation.batch_id == batch_id).delete(synchronize_session=False)
            session.query(BatchValuation).filter(BatchValuation.batch_id == batch_id).delete(synchronize_session=False)

            # Batch-scoped performance artifacts
            session.query(ProRataDistribution).filter(ProRataDistribution.batch_id == batch_id).delete(synchronize_session=False)
            session.query(Performance).filter(Performance.batch_id == batch_id).delete(synchronize_session=False)

            # Fund tables are batch-scoped
            session.query(FundPerformance).filter(FundPerformance.batch_id == batch_id).delete(synchronize_session=False)
            session.query(Fund).filter(Fund.batch_id == batch_id).delete(synchronize_session=False)

            # Shares are batch-scoped
            session.query(InvestorShares).filter(InvestorShares.batch_id == batch_id).delete(synchronize_session=False)

            # Withdrawals attributed to this batch — both DPRP oversubscription
            # refunds (always 1:1 with the batch they were generated for, see
            # apply_oversubscription_allocation) and ordinary investor-request
            # withdrawals whose batch_id points here. Deleting a batch used to
            # only NULL this FK, which left the withdrawal rows themselves behind
            # ("delete the batch, withdrawal still has the data in it"). Scoped
            # strictly by batch_id, so a client's withdrawals against their OTHER
            # batches are never touched.
            session.query(Withdrawal).filter(Withdrawal.batch_id == batch_id).delete(synchronize_session=False)

            # Delete investments first for explicit safety.
            session.query(Investment).filter(Investment.batch_id == batch_id).delete()
            deleted_share_class_id = batch.share_class_id
            session.delete(batch)

            # NavHistory is deliberately keyed by share_class_id, not batch_id —
            # a share class legitimately spans many batches over time, so
            # deleting one batch must NOT wipe out price history another batch
            # on the same class still needs. But once this was the LAST batch on
            # that share class, any NavHistory left for it is now provably
            # orphaned (nothing will ever read it again unless a future batch
            # reuses the class) — and leaving it behind is exactly what caused
            # a freshly-deployed replacement batch to inherit a stale "current"
            # NAV from the deleted batch's old test valuations, showing a
            # fabricated gain/loss that had nothing to do with the new batch.
            if deleted_share_class_id is not None:
                other_batch_on_class = session.query(Batch.id).filter(
                    Batch.share_class_id == deleted_share_class_id,
                    Batch.id != batch_id,
                ).first()
                if not other_batch_on_class:
                    from app.Funds.nav_history import NavHistory
                    session.query(NavHistory).filter(
                        NavHistory.share_class_id == deleted_share_class_id
                    ).delete(synchronize_session=False)

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
            prefetch = cls._prefetch_valuation_cascade(session, investments)
            investor_values = [cls._calculate_batch_investment_values(inv, batch, session, **prefetch) for inv in investments]
            # Reuse investor_values instead of a second full pass via _calculate_batch_current_standing
            # (which would recompute _calculate_batch_investment_values for every investment again).
            total_current_standing = sum(
                (Decimal(str(v.get("current_balance", 0))) for v in investor_values),
                Decimal("0"),
            )
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
                'share series': 'share_series',
                'share_series': 'share_series',
                'shares owned': 'shares_owned',
                'shares_owned': 'shares_owned',
                'currency': 'currency_type',
                'currency_type': 'currency_type',
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
                        share_series = str(row.get('share_series', '') or '').strip()
                        shares_owned_raw = row.get('shares_owned')
                        currency_type = str(row.get('currency_type', '') or '').strip().upper()
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
                        investment.share_series = share_series or core_fund.fund_name
                        investment.currency_type = currency_type if currency_type in ("USD", "KES") else Investment.currency_from_share_series(investment.share_series)
                        investment.original_deposit_amount = Decimal(str(amount_deposited))
                        investment.current_market_value = Decimal("0.00")
                        if shares_owned_raw is not None and not pd.isna(shares_owned_raw):
                            investment.shares_owned = Decimal(str(shares_owned_raw)).quantize(Decimal("0.0001"))
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
