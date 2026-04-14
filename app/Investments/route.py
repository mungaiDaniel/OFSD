from flask import request, Blueprint, jsonify, make_response, send_file, current_app
from flask_jwt_extended import jwt_required
from flask_cors import cross_origin
from app.database.database import db
from app.Investments.controllers import InvestmentController
from app.Investments.model import (
    Investment,
    EpochLedger,
    Withdrawal,
    EmailLog,
    normalize_withdrawal_status,
    WITHDRAWAL_STATUSES,
    FINAL_WITHDRAWAL_STATUSES,
)
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Valuation.model import ValuationRun
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from sqlalchemy import func
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import logging

logger = logging.getLogger(__name__)


def normalize_datetime_to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


investment_v1 = Blueprint("investment_v1", __name__, url_prefix='/')

# ==================== INVESTMENT ENDPOINTS ====================

@investment_v1.route('/api/v1/investments', methods=['POST'])
@jwt_required()
def add_investment():
    """
    Add a new investment to a batch
    
    Request Body:
    {
        "batch_id": 1,
        "investor_name": "John Doe",
        "investor_email": "john@example.com",
        "investor_phone": "+1234567890",
        "amount_deposited": 50000.00,
        "date_deposited": "2026-03-10T00:00:00"
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)
        
        session = db.session
        return InvestmentController.add_investment(data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/investments/<int:investment_id>', methods=['GET'])
@jwt_required()
def get_investment(investment_id):
    """Get a specific investment by ID"""
    try:
        session = db.session
        return InvestmentController.get_investment_by_id(investment_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/batches/<int:batch_id>/investments', methods=['GET'])
@jwt_required()
def get_batch_investments(batch_id):
    """Get all investments for a specific batch"""
    try:
        session = db.session
        return InvestmentController.get_investments_by_batch(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/investors', methods=['GET'])
@jwt_required()
def get_investor_directory():
    """Returns an investor directory listing with current balance standing."""
    try:
        all_investments = db.session.query(Investment).order_by(Investment.investor_name.asc()).all()

        investor_map = {}
        investor_ids = set()
        funds_per_client = {}
        batch_ids_per_client = {}

        for inv in all_investments:
            code = inv.internal_client_code
            fund_name = inv.fund_name or (inv.fund.fund_name if inv.fund else None)
            fund = fund_name.lower() if fund_name else "unknown"
            
            if code not in investor_map:
                investor_map[code] = {
                    "investor_name": inv.investor_name,
                    "internal_client_code": code,
                    "investor_email": inv.investor_email,
                    "investor_phone": inv.investor_phone,
                    "total_principal": 0.0, # Will represent Current Standing
                    "investments": 0,
                    "unique_batches": 0,
                    "last_email_status": None,
                    "last_email_timestamp": None,
                }

            investor_map[code]["investments"] += 1
            investor_ids.add(inv.id)
            if code not in batch_ids_per_client:
                batch_ids_per_client[code] = set()
            if inv.batch_id is not None:
                batch_ids_per_client[code].add(inv.batch_id)
            
            if code not in funds_per_client:
                funds_per_client[code] = {}
            if fund not in funds_per_client[code]:
                funds_per_client[code][fund] = 0.0
            funds_per_client[code][fund] += float(inv.amount_deposited)

        if investor_ids:
            logs = db.session.query(EmailLog).filter(EmailLog.investor_id.in_(investor_ids)).order_by(EmailLog.timestamp.desc()).all()
            last_state_by_investor = {}
            for log in logs:
                if log.investor_id not in last_state_by_investor:
                    last_state_by_investor[log.investor_id] = log

            for inv in all_investments:
                last_log = last_state_by_investor.get(inv.id)
                if last_log:
                    code = inv.internal_client_code
                    existing = investor_map.get(code)
                    if existing:
                        existing["last_email_status"] = last_log.status
                        existing["last_email_timestamp"] = last_log.timestamp.isoformat()

        for code, batch_ids in batch_ids_per_client.items():
            if code in investor_map:
                investor_map[code]["unique_batches"] = len(batch_ids)

        # Calculate current balance using the same BatchController method as portfolio endpoint
        # This ensures consistency between directory and individual portfolio views
        from app.Batch.controllers import BatchController
        
        investor_balances = {}
        for inv in all_investments:
            code = inv.internal_client_code
            batch_id = inv.batch_id
            batch = db.session.query(Batch).filter(Batch.id == batch_id).first() if batch_id else None
            
            if code not in investor_balances:
                investor_balances[code] = Decimal("0.00")
            
            try:
                inv_values = BatchController._calculate_batch_investment_values(inv, batch, db.session)
                investor_balances[code] += Decimal(str(inv_values["current_balance"]))
            except Exception as e:
                # Fallback: use deposited amount
                investor_balances[code] += Decimal(str(inv.amount_deposited))

        # Update each investor with their calculated balance
        for code, balance in investor_balances.items():
            if code in investor_map:
                investor_map[code]["total_principal"] = float(round(balance, 2))

        investors = list(investor_map.values())

        return make_response(jsonify({
            "status": 200,
            "message": "Investor directory retrieved",
            "count": len(investors),
            "data": investors
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/history', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True, methods=['GET', 'OPTIONS'])
def get_investor_history(client_code):
    """
    Returns an investor's chronological history of valuations.
    Withdrawals from the Withdrawal table are merged into the correct month
    so the Deposits vs Withdrawals chart displays actual outflow bars.
    
    CRITICAL: Only includes data up to the latest committed ValuationRun.
    This prevents unprocessed months (like October in 'Principal Only' state) from showing in charts.
    """
    try:
        session = db.session
        from sqlalchemy import func
        
        # ── CRITICAL: Find the LAST PROCESSED epoch (Sept 2026) ──
        max_chart_epoch = session.query(
            func.max(ValuationRun.epoch_end)
        ).filter(
            func.lower(ValuationRun.status) == "committed"
        ).scalar()
        
        ledgers = session.query(
            EpochLedger.epoch_start,
            EpochLedger.epoch_end,
            func.sum(EpochLedger.start_balance).label('start_balance'),
            func.sum(EpochLedger.withdrawals).label('withdrawals'),
            func.sum(EpochLedger.deposits).label('deposits'),
            func.sum(EpochLedger.profit).label('profit'),
            func.sum(EpochLedger.end_balance).label('end_balance')
        ).filter(
            EpochLedger.internal_client_code == client_code
        )
        
        # Restrict to max_chart_epoch (exclude unprocessed months)
        if max_chart_epoch:
            ledgers = ledgers.filter(EpochLedger.epoch_end <= max_chart_epoch)
        
        ledgers = ledgers.group_by(
            EpochLedger.epoch_start,
            EpochLedger.epoch_end
        ).order_by(
            EpochLedger.epoch_end.asc()
        ).all()

        # Query true total principal
        total_initial_deps = session.query(func.sum(Investment.amount_deposited)).filter(
            Investment.internal_client_code == client_code
        ).scalar()
        total_initial_deps = float(total_initial_deps or 0)

        # === FETCH ALL APPROVED WITHDRAWALS and bucket them by month ===
        wd_query = session.query(Withdrawal).filter(
            Withdrawal.internal_client_code == client_code,
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
        )
        all_approved_wds = wd_query.all()

        # Build a map: (year, month) -> total withdrawal amount
        wd_by_month = {}
        for w in all_approved_wds:
            if w.date_withdrawn:
                wd_dt = w.date_withdrawn.replace(tzinfo=None) if w.date_withdrawn.tzinfo else w.date_withdrawn
                key = (wd_dt.year, wd_dt.month)
                wd_by_month[key] = wd_by_month.get(key, 0.0) + float(w.amount)

        # === ALSO BUILD DEPOSITS BY MONTH FOR FRESH DEPOSITS ===
        inv_query = session.query(Investment).filter(
            Investment.internal_client_code == client_code
        )
        all_deposits = inv_query.all()
        
        dep_by_month = {}
        for inv in all_deposits:
            if inv.date_deposited:
                dep_dt = inv.date_deposited.replace(tzinfo=None) if inv.date_deposited.tzinfo else inv.date_deposited
                key = (dep_dt.year, dep_dt.month)
                dep_by_month[key] = dep_by_month.get(key, 0.0) + float(inv.amount_deposited)

        history = []
        epochs_covered_months = set()
        for i, l in enumerate(ledgers):
            start_bal = float(l.start_balance or 0)
            wd_ledger = float(l.withdrawals or 0)
            profit = float(l.profit or 0)
            deposits_val = float(l.deposits or 0)

            if i == 0 and deposits_val == 0 and total_initial_deps > 0:
                deposits_val = total_initial_deps

            epoch_end_naive = l.epoch_end.replace(tzinfo=None) if l.epoch_end and l.epoch_end.tzinfo else l.epoch_end
            epoch_key = (epoch_end_naive.year, epoch_end_naive.month) if epoch_end_naive else None
            if epoch_key:
                epochs_covered_months.add(epoch_key)

            wd_from_table = wd_by_month.get(epoch_key, 0.0) if epoch_key else 0.0
            wd_display = max(wd_ledger, wd_from_table)

            opening_capital = start_bal if start_bal > 0 else deposits_val
            perf_pct = (profit / opening_capital * 100) if opening_capital > 0 else 0.0

            month_name = l.epoch_end.strftime("%b '%y") if l.epoch_end else "Unknown"

            history.append({
                "sort_date": epoch_end_naive,
                "epoch_start": l.epoch_start.isoformat() if l.epoch_start else None,
                "epoch_end": l.epoch_end.isoformat() if l.epoch_end else None,
                "month_name": month_name,
                "start_balance": start_bal,
                "withdrawals": wd_display,
                "deposits": deposits_val,
                "profit": profit,
                "end_balance": float(l.end_balance or 0),
                "performance_pct": round(perf_pct, 2),
                "is_injected": False
            })

        from datetime import datetime, date
        for (yr, mo), wd_amt in sorted(wd_by_month.items()):
            if (yr, mo) not in epochs_covered_months:
                fake_dt = datetime(yr, mo, 28)
                month_name = fake_dt.strftime("%b '%y")
                dep_amt = dep_by_month.get((yr, mo), 0.0)
                history.append({
                    "sort_date": fake_dt,
                    "epoch_start": None,
                    "epoch_end": None,
                    "month_name": month_name,
                    "start_balance": 0.0,
                    "withdrawals": wd_amt,
                    "deposits": dep_amt,
                    "profit": 0.0,
                    "end_balance": 0.0,
                    "performance_pct": 0.0,
                    "is_injected": True
                })
        
        for (yr, mo), dep_amt in sorted(dep_by_month.items()):
            if (yr, mo) not in epochs_covered_months and (yr, mo) not in wd_by_month:
                fake_dt = datetime(yr, mo, 28)
                month_name = fake_dt.strftime("%b '%y")
                history.append({
                    "sort_date": fake_dt,
                    "epoch_start": None,
                    "epoch_end": None,
                    "month_name": month_name,
                    "start_balance": 0.0,
                    "withdrawals": 0.0,
                    "deposits": dep_amt,
                    "profit": 0.0,
                    "end_balance": 0.0,
                    "performance_pct": 0.0,
                    "is_injected": True
                })

        history.sort(key=lambda x: x.get("sort_date") or datetime.min)
        
        # Roll forward balances for injected months so chart doesn't crash to 0
        running_bal = 0.0
        for h in history:
            if h["start_balance"] == 0.0 and running_bal > 0.0:
                h["start_balance"] = running_bal
            if h["is_injected"]:
                h["end_balance"] = h["start_balance"] + h["deposits"] - h["withdrawals"] + h["profit"]
            running_bal = h["end_balance"]
            # Clean up temp key
            h.pop("sort_date", None)
            h.pop("is_injected", None)

        # Fallback: no epochs, show initial deposit
        if len(history) == 0 and total_initial_deps > 0:
            history.append({
                "epoch_start": None,
                "epoch_end": None,
                "month_name": "Initial",
                "start_balance": total_initial_deps,
                "withdrawals": 0.0,
                "deposits": total_initial_deps,
                "profit": 0.0,
                "end_balance": total_initial_deps,
                "performance_pct": 0.0
            })

        return make_response(jsonify({
            "status": 200,
            "data": history
        }), 200)
    except Exception as e:
        pass
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/portfolio', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True, methods=['GET', 'OPTIONS'])
def get_investor_portfolio_aggregated(client_code):
    """
    Returns an investor's aggregated portfolio across all batches and funds.
    Groups holdings by batch/fund and shows total principal and valuation data.
    
    Response:
    {
        "status": 200,
        "data": {
            "client_code": "AXIOM-001",
            "investor_name": "John Doe",
            "total_principal": 150000.00,
            "unique_batches": 2,
            "holdings": [
                {
                    "batch_name": "Batch Q1 2024",
                    "batch_id": 1,
                    "fund_name": "Fund A",
                    "fund_id": 1,
                    "investments_count": 2,
                    "total_principal": 50000.00,
                    "latest_valuation": {
                        "epoch_end": "2026-04-30",
                        "end_balance": 52500.00,
                        "profit": 2500.00,
                        "performance_rate": 0.05
                    }
                }
            ]
        }
    }
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return make_response('', 204)
    
    # JWT required for actual GET request
    from flask_jwt_extended import verify_jwt_in_request
    verify_jwt_in_request()
    try:
        # Get all investments for this client (case-insensitive)
        investments = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).order_by(Investment.investor_name.asc()).all()
        
        if not investments:
            return make_response(jsonify({
                "status": 404,
                "message": "Investor not found"
            }), 404)
        
        investor_name = investments[0].investor_name
        
        # Group investments by batch and fund
        holdings_map = {}
        total_principal = Decimal("0.00")
        
        for inv in investments:
            batch_id = inv.batch_id
            fund_name = (inv.fund.fund_name if inv.fund else inv.fund_name) or "Unknown"
            fund_id = inv.fund_id
            
            key = (batch_id, fund_name, fund_id)
            
            if key not in holdings_map:
                batch = db.session.query(Batch).filter(Batch.id == batch_id).first() if batch_id else None
                holdings_map[key] = {
                    "batch_id": batch_id,
                    "batch_name": batch.batch_name if batch else "Unknown",
                    "batch_type": "Atomic Batch",
                    "fund_id": fund_id,
                    "fund_name": fund_name,
                    "investments": [],
                    "total_principal": Decimal("0.00")
                }
            
            holdings_map[key]["investments"].append(inv)
            holdings_map[key]["total_principal"] += inv.amount_deposited
            total_principal += inv.amount_deposited
        
        # Build holdings response with aggregated data using atomic batch simulation
        holdings = []
        from app.Batch.controllers import BatchController
        
        for (batch_id, fund_name, fund_id), holding in holdings_map.items():
            batch_id_val = batch_id
            total_principal_val = holding["total_principal"]
            investments_count = len(holding["investments"])
            batch = db.session.query(Batch).filter(Batch.id == batch_id).first() if batch_id else None
            batch_name = batch.batch_name if batch else holding["batch_name"]
            
            # Use the simulated balance for each investment in this batch
            valuation_data = None
            batch_total_profit = Decimal("0")
            batch_total_withdrawals = Decimal("0")
            batch_end_balance = Decimal("0")
            
            try:
                for inv in holding["investments"]:
                    # Use the batch controller's simulation method for accurate per-investment balances
                    inv_values = BatchController._calculate_batch_investment_values(inv, batch, db.session)
                    batch_end_balance += Decimal(str(inv_values["current_balance"]))
                    batch_total_profit += Decimal(str(inv_values["profit"]))
                    batch_total_withdrawals += Decimal(str(inv_values["withdrawals"]))
                
                # Get latest epoch for reference metadata
                latest_epoch = db.session.query(EpochLedger).filter(
                    EpochLedger.internal_client_code == client_code,
                    func.lower(EpochLedger.fund_name) == func.lower(fund_name),
                ).order_by(EpochLedger.epoch_end.desc()).first()
                
                if latest_epoch:
                    # ✅ FIX: Use start_balance directly from ledger (NOT calculated)
                    # Also fetch performance_rate from ValuationRun for accuracy
                    performance_rate = float(latest_epoch.performance_rate * 100) if latest_epoch.performance_rate else 0.0
                    
                    # Try to get actual performance_rate from ValuationRun for accuracy
                    vr = db.session.query(ValuationRun).join(
                        CoreFund, ValuationRun.core_fund_id == CoreFund.id
                    ).filter(
                        ValuationRun.epoch_end == latest_epoch.epoch_end,
                        func.lower(CoreFund.fund_name) == func.lower(fund_name)
                    ).first()
                    if vr:
                        performance_rate = float(vr.performance_rate * 100)
                    
                    valuation_data = {
                        "epoch_start": latest_epoch.epoch_start.isoformat(),
                        "epoch_end": latest_epoch.epoch_end.isoformat(),
                        # ✅ FIX: Use start_balance from ledger (opening balance, NOT principal - profit)
                        "start_balance": float(latest_epoch.start_balance or 0),
                        "deposits": float(total_principal_val),
                        "withdrawals": float(batch_total_withdrawals),
                        "profit": float(batch_total_profit),
                        "end_balance": float(round(batch_end_balance, 2)),
                        # ✅ NEW: Include actual performance_rate from database
                        "performance_rate_percent": performance_rate,
                    }
                else:
                    # No valuation yet - use principal only
                    valuation_data = {
                        "epoch_start": None,
                        "epoch_end": None,
                        "start_balance": float(total_principal_val),
                        "deposits": float(total_principal_val),
                        "withdrawals": 0.0,
                        "profit": 0.0,
                        "end_balance": float(total_principal_val),
                        "performance_rate_percent": 0.0,
                    }
            except Exception as calc_err:
                pass
                valuation_data = {
                    "epoch_start": None,
                    "epoch_end": None,
                    "start_balance": float(total_principal_val),
                    "deposits": float(total_principal_val),
                    "withdrawals": 0.0,
                    "profit": 0.0,
                    "end_balance": float(total_principal_val),
                    "performance_rate_percent": 0.0,
                }

            holdings.append({
                "batch_id": batch_id_val,
                "batch_name": batch_name,
                "batch_type": "Atomic Batch",
                "fund_id": fund_id,
                "fund_name": fund_name,
                "investments_count": investments_count,
                "total_principal": float(total_principal_val),
                "latest_valuation": valuation_data
            })

        # Sort by batch_id, then fund_name
        holdings.sort(key=lambda x: (x["batch_id"] or 0, x["fund_name"]))
        
        current_balance = round(sum(
            float(h["latest_valuation"]["end_balance"] if h["latest_valuation"] else h["total_principal"]) for h in holdings
        ), 2)
        total_profit = round(current_balance - float(total_principal), 2)

        data = {
            "client_code": client_code,
            "investor_name": investor_name,
            "initial_investment": float(total_principal),
            "total_principal": float(total_principal),
            "current_balance": current_balance,
            "head_office_total": current_balance,
            "total_profit": float(total_profit),
            "unique_batches": len(set(h["batch_id"] for h in holdings)),
            "holdings": holdings
        }
        
        return make_response(jsonify({
            "status": 200,
            "message": "Investor portfolio retrieved",
            "data": data
        }), 200)
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        pass
        return make_response(jsonify({
            "status": 500,
            "message": f"Portfolio error: {error_msg}",
            "debug": error_trace
        }), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/email-logs', methods=['GET'])
@jwt_required()
def get_investor_email_logs(client_code):
    """Returns email logs for an investor identified by internal_client_code."""
    try:
        investments = db.session.query(Investment).filter(Investment.internal_client_code == client_code).all()
        if not investments:
            return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)

        investor_ids = [inv.id for inv in investments]
        logs = db.session.query(EmailLog).filter(EmailLog.investor_id.in_(investor_ids)).order_by(EmailLog.timestamp.desc()).all()

        log_items = [{
            "id": log.id,
            "investor_id": log.investor_id,
            "batch_id": log.batch_id,
            "status": log.status,
            "error_message": log.error_message,
            "timestamp": log.timestamp.isoformat(),
            "retry_count": log.retry_count,
        } for log in logs]

        return make_response(jsonify({
            "status": 200,
            "message": "Investor email logs retrieved",
            "count": len(log_items),
            "data": log_items
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/batches/<int:batch_id>/investments', methods=['POST'])
@jwt_required()
def add_investment_to_batch(batch_id):
    """
    Add a new investment to a specific batch
    
    Request Body:
    {
        "investor_name": "John Doe",
        "investor_email": "john@example.com",
        "investor_phone": "+1234567890",
        "amount_deposited": 50000.00,
        "date_deposited": "2026-03-10T00:00:00"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)
        
        # Add batch_id to data
        data['batch_id'] = batch_id
        
        session = db.session
        return InvestmentController.add_investment(data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/investments/<int:investment_id>', methods=['PUT'])
@jwt_required()
def update_investment(investment_id):
    """
    Update an investment
    
    Request Body (optional fields):
    {
        "investor_name": "Jane Doe",
        "investor_email": "jane@example.com",
        "investor_phone": "+0987654321",
        "amount_deposited": 60000.00,
        "date_deposited": "2026-03-05T00:00:00"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)
        
        session = db.session
        return InvestmentController.update_investment(investment_id, data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/investments/<int:investment_id>', methods=['DELETE'])
@jwt_required()
def delete_investment(investment_id):
    """Delete an investment"""
    try:
        session = db.session
        return InvestmentController.delete_investment(investment_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/investments/upload', methods=['POST'])
@jwt_required()
def upload_investments_excel():
    """
    Upload an Excel file of investors for a specific batch.

    Accepts multipart/form-data with:
      - batch_id  (form field, integer)
      - file      (binary, .xlsx / .xls / .csv)

    Expected Excel columns:
      - Client Name             -> investor_name
      - Internal client code    -> internal_client_code
      - Amount(usd)             -> amount_deposited
      - funds                   -> fund_name

    Uses upsert logic: updates existing rows matched by
    (internal_client_code, batch_id); inserts new ones.
    """
    try:
        # Validate batch_id form field
        batch_id_raw = request.form.get('batch_id')
        if not batch_id_raw:
            return make_response(jsonify({
                "status": 400,
                "message": "batch_id is required as a form field"
            }), 400)

        try:
            batch_id = int(batch_id_raw)
        except ValueError:
            return make_response(jsonify({
                "status": 400,
                "message": "batch_id must be an integer"
            }), 400)

        # Validate file
        if 'file' not in request.files:
            return make_response(jsonify({
                "status": 400,
                "message": "No file part in the request"
            }), 400)

        file = request.files['file']
        if file.filename == '':
            return make_response(jsonify({
                "status": 400,
                "message": "No file selected"
            }), 400)

        session = db.session
        return InvestmentController.upload_excel_for_batch(batch_id, file, session)

    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/statement', methods=['GET'])
@jwt_required()
def get_investor_statement(client_code):
    """
    Investor statement endpoint for epoch-ledger compounding history.

    Query params:
      - fund_id (optional): filter to a specific fund_id (by matching fund_name from investments)

    Response:
    {
      "status": 200,
      "data": [
        { "epoch_start": "...", "epoch_end": "...", "opening": 0, "profit": 0, "closing": 0, ... }
      ]
    }
    """
    try:
        fund_id_raw = request.args.get('fund_id')
        period_raw = (request.args.get('period') or '').strip()
        period_dt = None
        if period_raw:
            # Accept ISO date or datetime; we match against EpochLedger.epoch_end
            try:
                period_dt = datetime.fromisoformat(period_raw.replace('Z', '+00:00'))
            except Exception:
                return make_response(jsonify({"status": 400, "message": "period must be an ISO date/datetime (e.g. 2026-03-31)"}), 400)

        fund_name_filter = None
        if fund_id_raw:
            try:
                fund_id = int(fund_id_raw)
            except ValueError:
                return make_response(jsonify({"status": 400, "message": "fund_id must be an integer"}), 400)

            # Resolve fund_name from investments table (fund_id is stable)
            inv = db.session.query(InvestmentController.model).filter(
                InvestmentController.model.fund_id == fund_id
            ).first()
            if not inv:
                return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)
            fund_name_filter = inv.fund_name

        q = db.session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == client_code
        )
        if fund_name_filter:
            q = q.filter(func.lower(EpochLedger.fund_name) == fund_name_filter.lower())
        if period_dt is not None:
            q = q.filter(EpochLedger.epoch_end == period_dt)

        rows = q.order_by(EpochLedger.epoch_start.asc()).all()
        if not rows:
            empty_data = {
                "client_code": client_code,
                "investor_name": None,
                "funds": [],
                "summary": {"opening_balance": 0.0, "net_growth": 0.0, "closing_balance": 0.0},
                "periods": [],
                "history": [],
                "latest_audit_hash": None,
            }
            return make_response(jsonify({
                "status": 200,
                "message": "Statement retrieved",
                "count": 0,
                "statement": empty_data,
                "data": empty_data,
            }), 200)

        # Resolve investor name (most recent Investment row)
        inv_latest = db.session.query(Investment).filter(
            Investment.internal_client_code == client_code
        ).order_by(Investment.date_updated.desc(), Investment.id.desc()).first()
        investor_name = inv_latest.investor_name if inv_latest else None

        # Map fund_name -> CoreFund.id (so we can pull ValuationRun.performance_rate per period)
        fund_names = sorted({(r.fund_name or "").strip() for r in rows if (r.fund_name or "").strip()})
        core_funds = db.session.query(CoreFund).filter(
            func.lower(CoreFund.fund_name).in_([fn.lower() for fn in fund_names])
        ).all() if fund_names else []
        core_by_lower = {cf.fund_name.lower(): cf for cf in core_funds}

        # Preload valuation runs for these funds (keyed by (core_fund_id, epoch_start, epoch_end))
        core_ids = [cf.id for cf in core_funds]
        vr_rows = db.session.query(ValuationRun).filter(
            ValuationRun.core_fund_id.in_(core_ids),
            ValuationRun.status == "Committed",
        ).all() if core_ids else []
        vr_by_key = {(vr.core_fund_id, vr.epoch_start, vr.epoch_end): vr for vr in vr_rows}

        # Periods (epoch-level entries) + running balance check
        periods = []
        running_balance = None
        history = []

        for r in rows:
            fund_name = (r.fund_name or "").strip()
            cf = core_by_lower.get(fund_name.lower()) if fund_name else None
            vr = vr_by_key.get((cf.id, r.epoch_start, r.epoch_end)) if cf else None
            performance_rate_percent = float(vr.performance_rate) * 100.0 if vr else (float(r.performance_rate) * 100.0)

            start_bal = Decimal(str(r.start_balance))
            deps = Decimal(str(r.deposits))
            wds = Decimal(str(r.withdrawals))
            prof = Decimal(str(r.profit))
            end_bal = Decimal(str(r.end_balance))

            if running_balance is None:
                running_balance = start_bal

            # Calculate running end (then trust ledger end_balance as authoritative output)
            computed_end = running_balance + deps - wds + prof
            running_balance = end_bal

            periods.append({
                "id": r.id,
                "fund_name": fund_name,
                "epoch_start": r.epoch_start.isoformat(),
                "epoch_end": r.epoch_end.isoformat(),
                "performance_rate_percent": round(performance_rate_percent, 4),
                "opening": float(start_bal),
                "deposits": float(deps),
                "withdrawals": float(wds),
                "profit": float(prof),
                "closing": float(end_bal),
                "previous_hash": r.previous_hash,
                "current_hash": r.current_hash,
                "computed_end_balance": float(computed_end),
                "computed_matches_ledger": abs(computed_end - end_bal) <= Decimal("0.01"),
            })

            # History table rows (epoch end date)
            epoch_date = r.epoch_end.isoformat()
            if deps != 0:
                history.append({
                    "date": epoch_date,
                    "description": f"Deposits ({fund_name})",
                    "amount": float(deps),
                    "running_balance": float(end_bal),  # end-of-period balance
                })
            if wds != 0:
                history.append({
                    "date": epoch_date,
                    "description": f"Withdrawals ({fund_name})",
                    "amount": float(-wds),
                    "running_balance": float(end_bal),
                })
            if prof != 0:
                history.append({
                    "date": epoch_date,
                    "description": f"Performance {round(performance_rate_percent, 4)}% ({fund_name})",
                    "amount": float(prof),
                    "running_balance": float(end_bal),
                })

        opening_balance = float(rows[0].start_balance)
        closing_balance = float(rows[-1].end_balance)
        net_growth = float(sum((Decimal(str(r.profit)) for r in rows), Decimal("0.00")))
        latest_hash = rows[-1].current_hash

        data = {
            "client_code": client_code,
            "investor_name": investor_name,
            "funds": fund_names,
            "summary": {
                "opening_balance": round(opening_balance, 2),
                "net_growth": round(net_growth, 2),
                "closing_balance": round(closing_balance, 2),
            },
            "periods": periods,
            "history": history,
            "latest_audit_hash": latest_hash,
        }

        return make_response(jsonify({
            "status": 200,
            "message": "Statement retrieved",
            "count": len(periods),
            "data": data
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/statement/pdf', methods=['GET'])
@jwt_required()
def download_investor_statement_pdf(client_code):
    """
    Generate a branded investor statement PDF that matches the client statement layout.
    """
    try:
        as_of = request.args.get("as_of")
        
        # If as_of is provided, we fetch the specific epoch ledger entries for that date
        if as_of:
            try:
                target_date = datetime.fromisoformat(as_of.replace('Z', '+00:00'))
                
                # Fetch all investments for this client
                investments = db.session.query(Investment).filter(
                    Investment.internal_client_code == client_code
                ).all()

                if not investments:
                    return make_response(jsonify({"status": 404, "message": f"No investments found for {client_code}"}), 404)

                investor_name = investments[0].investor_name
                
                # Group investments by batch and compute values dynamically
                from app.Batch.controllers import BatchController
                
                holdings_map = {}
                target_dt_utc = target_date.replace(tzinfo=timezone.utc) if target_date.tzinfo is None else target_date.astimezone(timezone.utc)
                
                epoch_start = None
                epoch_end = None
                
                for inv in investments:
                    batch = db.session.query(Batch).filter(Batch.id == inv.batch_id).first() if inv.batch_id else None
                    fund_name = (inv.fund.fund_name if inv.fund else inv.fund_name) or "Unknown"
                    batch_id = inv.batch_id
                    
                    key = (batch_id, fund_name)
                    if key not in holdings_map:
                        holdings_map[key] = {
                            "batch_id": batch_id,
                            "batch_name": batch.batch_name if batch else "Unknown",
                            "fund_name": fund_name,
                            "deposits": 0.0,
                            "withdrawals": 0.0,
                            "profit": 0.0,
                            "end_balance": 0.0,
                            "has_data": False,
                            "epoch_start": None,
                            "epoch_end": None,
                        }

                    # Retrieve true simulated historical states
                    sim_states = BatchController._simulate_client_fund_balances(inv, db.session)
                    if sim_states and inv.id in sim_states:
                        state = sim_states[inv.id]
                        
                        # Find the matching epoch in the history for the target date
                        history = state.get("history", [])
                        for h in history:
                            h_end_utc = h["epoch_end"].replace(tzinfo=timezone.utc) if h["epoch_end"].tzinfo is None else h["epoch_end"].astimezone(timezone.utc)
                            
                            # Check if the epoch ending year and month matches
                            if h_end_utc.year == target_dt_utc.year and h_end_utc.month == target_dt_utc.month:
                                holdings_map[key]["deposits"] += float(h["deposit"])
                                holdings_map[key]["withdrawals"] += float(h["withdrawal"])
                                holdings_map[key]["profit"] += float(h["profit"])
                                holdings_map[key]["end_balance"] += float(h["end_balance"])
                                holdings_map[key]["has_data"] = True
                                
                                # Estimate start time for display (can just subtract ~30 days if not tracked)
                                if not epoch_end:
                                    epoch_end = h["epoch_end"]
                                    # Fallback start date approximation for display
                                    import datetime as dt_lib
                                    epoch_start = epoch_end.replace(day=1)
                                break
                
                # Filter holdings that actually existed during this epoch
                holdings = []
                for holding in holdings_map.values():
                    if holding["has_data"]:
                        holdings.append({
                            "batch_id": holding["batch_id"],
                            "batch_name": holding["batch_name"],
                            "fund_name": holding["fund_name"],
                            "latest_valuation": {
                                "deposits": holding["deposits"],
                                "withdrawals": holding["withdrawals"],
                                "profit": holding["profit"],
                                "end_balance": holding["end_balance"],
                            }
                        })
                
                if not holdings:
                    return make_response(jsonify({"status": 404, "message": f"No active holdings found for {as_of}"}), 404)

                unique_batches = len(set(h["batch_id"] for h in holdings))

                total_deposits = sum(Decimal(str(h["latest_valuation"]["deposits"])) for h in holdings)
                total_withdrawals = sum(Decimal(str(h["latest_valuation"]["withdrawals"])) for h in holdings)
                total_current_value = sum(Decimal(str(h["latest_valuation"]["end_balance"])) for h in holdings)
                total_profit = sum(Decimal(str(h["latest_valuation"]["profit"])) for h in holdings)
                total_principal = sum(
                    Decimal(str(h["latest_valuation"]["end_balance"]))
                    - Decimal(str(h["latest_valuation"]["profit"]))
                    + Decimal(str(h["latest_valuation"]["withdrawals"]))
                    for h in holdings
                )
                
                if epoch_start and epoch_end:
                    period_range = f"{epoch_start.strftime('%b %d, %Y')} - {epoch_end.strftime('%b %d, %Y')}"
                    statement_date = epoch_end.strftime('%B %d, %Y')
                else:
                    period_range = "Current Portfolio"
                    statement_date = target_dt_utc.strftime('%B %d, %Y')
                    
            except Exception as e:
                import traceback; traceback.print_exc()
                return make_response(jsonify({"status": 400, "message": f"Invalid as_of processing: {str(e)}"}), 400)
        else:
            # Fallback to current portfolio aggregation (current behavior)
            try:
                json_res = get_investor_portfolio_aggregated(client_code)
                payload = json_res.get_json() if hasattr(json_res, "get_json") else None
                if not payload or payload.get("status") != 200:
                    error_msg = payload.get("message") if payload else "Failed to fetch investor portfolio"
                    print(f"❌ Portfolio aggregation failed for {client_code}: {error_msg}")
                    return json_res

                data = payload.get("data") or {}
                investor_name = data.get("investor_name") or "Investor"
                holdings = data.get("holdings") or []
                unique_batches = data.get("unique_batches") or 0
                
                if not holdings:
                    return make_response(jsonify({
                        "status": 404, 
                        "message": f"No holdings found for investor {client_code}"
                    }), 404)
                
                total_principal = Decimal(str(data.get("total_principal") or 0))
            except Exception as agg_err:
                print(f"❌ Portfolio aggregation exception for {client_code}: {str(agg_err)}")
                return make_response(jsonify({
                    "status": 500,
                    "message": f"Failed to aggregate portfolio: {str(agg_err)}"
                }), 500)
            
            # Derive statement dates from available valuations
            valuation_dates = [h.get("latest_valuation", {}).get("epoch_end") for h in holdings if h.get("latest_valuation", {}).get("epoch_end")]
            period_range = "Current Portfolio"
            statement_date = datetime.now().strftime('%B %d, %Y')
            
            if valuation_dates:
                try:
                    parsed_dates = [datetime.fromisoformat(d) for d in valuation_dates if d]
                    if parsed_dates:
                        max_date = max(parsed_dates)
                        period_range = f"{min(parsed_dates).strftime('%b %d, %Y')} - {max_date.strftime('%b %d, %Y')}"
                        statement_date = max_date.strftime('%B %d, %Y')
                except Exception as date_err:
                    print(f"⚠️  Warning: Could not parse valuation dates for {client_code}: {str(date_err)}")
                    period_range = "Current Portfolio"

            total_deposits = sum(Decimal(str(h.get("latest_valuation", {}).get("deposits") or 0)) for h in holdings)
            total_withdrawals = sum(Decimal(str(h.get("latest_valuation", {}).get("withdrawals") or 0)) for h in holdings)
            total_current_value = sum(Decimal(str(h.get("latest_valuation", {}).get("end_balance") or 0)) for h in holdings)
            total_profit = sum(Decimal(str(h.get("latest_valuation", {}).get("profit") or 0)) for h in holdings)
            total_principal = (
                total_current_value - total_profit + total_withdrawals
            )

        code = client_code

        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'InvestorTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'InvestorHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        )
        section_heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            leading=13,
        )
        small_right_style = ParagraphStyle(
            'SmallRight',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
            alignment=2,
            leading=12,
        )

        # Header with logo image
        logo_path = Path(__file__).resolve().parents[2].parent / 'ofds-frontend' / 'public' / 'AIBlight.png'
        logo_flowable = None
        if logo_path.exists():
            logo_flowable = Image(str(logo_path), width=150, height=45)
            logo_flowable.hAlign = 'LEFT'

        head_office_html = (
            "<para align=right>"
            "<font size=9><b>HEAD OFFICE</b></font><br/>"
            "<font size=8>The Promenade, 5th Floor | General Mathenge Rd</font><br/>"
            "<font size=8>P.O. Box 43676-00100 | Nairobi | Kenya</font><br/>"
            "<font size=8>T: 0711047000 | M: 0790404571</font><br/>"
            "<font size=8>W: www.aib-axysafrica.com</font>"
            "</para>"
        )
        header_cells = [
            logo_flowable if logo_flowable is not None else Paragraph('<font size=18><b>AIB-AXYS Africa</b></font>', title_style),
            Paragraph(head_office_html, small_right_style)
        ]
        header_table = Table([header_cells], colWidths=[3.8 * inch, 3.7 * inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.04 * inch))
        story.append(Table([['']], colWidths=[7.5 * inch], style=[('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#00005b'))]))
        story.append(Spacer(1, 0.14 * inch))
        story.append(Paragraph('CLIENT STATEMENT', heading_style))
        story.append(Spacer(1, 0.18 * inch))

        info_data = [
            ['Client Code', f': {code}', 'Statement Date', f': {statement_date}'],
            ['Client Name', f': {investor_name}', 'Number of Holdings', f': {len(holdings)}'],
            ['Batches', f': {unique_batches}', 'Statement Period', ': MTD'],
            ['Period Range', f': {period_range}', '', ''],
        ]
        info_table = Table(info_data, colWidths=[1.2 * inch, 1.7 * inch, 1.2 * inch, 3.4 * inch])
        info_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -2), 'LEFT'),
            ('ALIGN', (3, 0), (3, -2), 'LEFT'),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.25 * inch))

        # Account summary
        summary_data = [
            ['Total Principal Invested', f'${total_principal:,.2f}'],
            ['Deposits (YTD)', f'${total_deposits:,.2f}'],
            ['Withdrawals (YTD)', f'${total_withdrawals:,.2f}'],
            ['Current Balance', f'${total_current_value:,.2f}'],
            ['Profit/Loss', f'${total_profit:,.2f}'],
        ]
        summary_table = Table(summary_data, colWidths=[5.2 * inch, 2.3 * inch])
        summary_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(Paragraph('Account Summary (USD)', section_heading_style))
        story.append(summary_table)
        story.append(Spacer(1, 0.25 * inch))

        # Holdings details
        holdings_rows = [[
            'Batch ID', 'Batch', 'Fund', 'Principal', 'Withdrawals', 'Current Value', 'Profit/Loss', 'Return %'
        ]]
        try:
            for holding in holdings:
                latest = holding.get('latest_valuation') or {}
                withdrawals = Decimal(str(latest.get('withdrawals') or 0))
                current_value = Decimal(str(latest.get('end_balance') or 0))
                profit_loss = Decimal(str(latest.get('profit') or 0))
                principal = current_value - profit_loss + withdrawals
                return_pct = (profit_loss / principal * 100) if principal > 0 else Decimal('0.00')

                holdings_rows.append([
                    str(holding.get('batch_id') or '—'),
                    holding.get('batch_name') or '—',
                    holding.get('fund_name') or '—',
                    f'${principal:,.2f}',
                    f'({withdrawals:,.2f})' if withdrawals > 0 else f'${withdrawals:,.2f}',
                    f'${current_value:,.2f}',
                    f'${profit_loss:,.2f}',
                    f'{return_pct:.2f}%'
                ])
        except Exception as row_err:
            print(f"⚠️  Error building holdings row for {client_code}: {str(row_err)}")
            holdings_rows = [['Batch ID', 'Batch', 'Fund', 'Principal', 'Withdrawals', 'Current Value', 'Profit/Loss', 'Return %']]

        if len(holdings_rows) == 1:
            holdings_rows.append(['—', 'No holdings', '$0.00', '$0.00', '$0.00', '$0.00', '0.00%', '0.00%'])

        # Add a final Head Office total row
        holdings_rows.append(['', 'HEAD OFFICE TOTAL', '', '', f'${total_withdrawals:,.2f}', f'${total_current_value:,.2f}', f'${total_profit:,.2f}', ''])

        holdings_table = Table(holdings_rows, colWidths=[0.7 * inch, 1.1 * inch, 1.4 * inch, 1.0 * inch, 0.9 * inch, 1.1 * inch, 1.0 * inch, 0.8 * inch])
        holdings_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
            ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#00005b')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph('Holdings Details', section_heading_style))
        story.append(holdings_table)
        story.append(Spacer(1, 0.15 * inch))

        # Reconciliation
        reconciliation_data = [
            ['Opening Balance', f'${(total_current_value - total_profit - total_deposits + total_withdrawals):,.2f}'],
            ['Deposits', f'${total_deposits:,.2f}'],
            ['Withdrawals', f'(${total_withdrawals:,.2f})'],
            ['Performance/Profit', f'${total_profit:,.2f}'],
            ['Closing Balance', f'${total_current_value:,.2f}'],
        ]
        reconciliation_table = Table(reconciliation_data, colWidths=[3.5 * inch, 3.5 * inch])
        reconciliation_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f9f9f9')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(Paragraph('Reconciliation', section_heading_style))
        story.append(reconciliation_table)
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(
            'Formula: Opening + Deposits - Withdrawals + Profit = Closing Balance',
            ParagraphStyle('ReconciliationNote', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#666666'))
        ))
        story.append(Spacer(1, 0.25 * inch))

        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            leading=12,
        )
        story.append(Paragraph(
            '<b>Disclaimer:</b> This statement is provided for informational purposes only. All figures are subject to change and may not reflect real-time data.',
            footer_style
        ))
        story.append(Paragraph(
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
            footer_style
        ))

        doc.build(story)
        pdf_buffer.seek(0)

        filename = f"investor-statement-{code}.pdf"
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n❌ Statement PDF generation failed for {client_code}:")
        print(f"Error: {str(e)}")
        print(f"Traceback:\n{error_trace}\n")
        return make_response(jsonify({'status': 500, 'message': f'Error: {str(e)}'}), 500)


# ==================== INVESTOR REGISTRY (GLOBAL) ====================

@investment_v1.route('/api/v1/investors', methods=['GET'])
@jwt_required()
def list_investors_registry():
    """
    Global investor registry (distinct internal_client_code across all batches).
    """
    try:
        session = db.session

        rows = session.query(
            Investment.internal_client_code.label("client_code"),
            func.max(Investment.investor_name).label("investor_name"),
            func.max(Investment.investor_email).label("investor_email"),
            func.max(Investment.investor_phone).label("investor_phone"),
            func.count(func.distinct(Investment.batch_id)).label("batches_count"),
            func.coalesce(func.sum(Investment.amount_deposited), 0).label("total_deposited"),
        ).group_by(
            Investment.internal_client_code
        ).order_by(
            Investment.internal_client_code.asc()
        ).all()

        data = [
            {
                "client_code": r.client_code,
                "investor_name": r.investor_name,
                "investor_email": r.investor_email,
                "investor_phone": r.investor_phone,
                "batches_count": int(r.batches_count or 0),
                "total_deposited": float(r.total_deposited or 0),
            }
            for r in rows
        ]

        return make_response(jsonify({"status": 200, "message": "Investors retrieved", "count": len(data), "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>', methods=['GET'])
@jwt_required()
def get_investor_profile(client_code):
    """
    Investor profile: investments history + epoch ledger summary.
    """
    try:
        session = db.session

        investments = session.query(Investment).filter(
            Investment.internal_client_code == client_code
        ).order_by(Investment.date_deposited.asc()).all()

        if not investments:
            return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)

        ledger = session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == client_code
        ).order_by(EpochLedger.epoch_start.asc()).all()

        inv_data = [
            {
                "id": inv.id,
                "batch_id": inv.batch_id,
                "fund_name": inv.fund_name,
                "amount_deposited": float(inv.amount_deposited),
                "date_deposited": inv.date_deposited.isoformat() if inv.date_deposited else None,
                "date_transferred": inv.date_transferred.isoformat() if inv.date_transferred else None,
            }
            for inv in investments
        ]

        ledger_data = [
            {
                "id": r.id,
                "fund_name": r.fund_name,
                "epoch_start": r.epoch_start.isoformat(),
                "epoch_end": r.epoch_end.isoformat(),
                "opening": float(r.start_balance),
                "profit": float(r.profit),
                "closing": float(r.end_balance),
            }
            for r in ledger
        ]

        total_profit = sum((float(r.profit) for r in ledger), 0.0)
        current_value = float(ledger[-1].end_balance) if ledger else float(sum(inv.amount_deposited for inv in investments))

        profile = {
            "client_code": client_code,
            "internal_client_code": client_code,
            "investor_name": investments[-1].investor_name,
            "investor_email": investments[-1].investor_email,
            "investor_phone": investments[-1].investor_phone,
            "total_deposited": float(sum(inv.amount_deposited for inv in investments)),
            "total_profit": float(total_profit),
            "current_value": float(current_value),
            "investments": inv_data,
            "ledger": ledger_data
        }
        return make_response(jsonify({
            "status": 200,
            "message": "Investor profile retrieved",
            "internal_client_code": client_code,
            "investor_name": investments[-1].investor_name,
            "investor_email": investments[-1].investor_email,
            "data": profile,
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

@investment_v1.route('/api/v1/investors/<string:client_code>/statements', methods=['GET'])
@jwt_required()
def get_investor_statements(client_code):
    """
    Returns a unified chronological list of all 'statements' for an investor,
    including deposit events, monthly ledger reports, and withdrawals.
    
    Deposit Event Sequencing:
    - April 2026: Initial $50,000 deposit
    - September 2026: $50,000 top-up deposit
    - October 2026: $30,000 top-up deposit
    - For Daniel Mungai (ATIUM-009): Only October deposit
    """
    try:
        session = db.session
        
        # 1. Fetch data (case-insensitive client code matching)
        investments = session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).all()
        
        ledger_entries = session.query(EpochLedger).filter(
            func.lower(EpochLedger.internal_client_code) == func.lower(client_code)
        ).all()
        
        withdrawals = session.query(Withdrawal).filter(
            func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES)
        ).all()

        # Calculate total principal (sum of all deposits)
        total_principal = sum(float(inv.amount_deposited) for inv in investments)
        
        statements = []
        
        # === ADD DEPOSIT EVENTS ===
        # Group investments by batch to create logical deposit entries
        deposit_by_batch = {}
        for inv in investments:
            batch_id = inv.batch_id
            if batch_id not in deposit_by_batch:
                deposit_by_batch[batch_id] = {
                    "amount": 0.0,
                    "date": inv.date_deposited,
                    "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                }
            deposit_by_batch[batch_id]["amount"] += float(inv.amount_deposited)
        
        # Create deposit statement entries
        # Fetch batch names for deposit events
        batch_names = {}
        batch_ids = [bid for bid in deposit_by_batch.keys() if bid is not None]
        if batch_ids:
            batches = db.session.query(Batch.id, Batch.batch_name).filter(Batch.id.in_(set(batch_ids))).all()
            batch_names = {b.id: b.batch_name for b in batches}

        for batch_id, deposit_info in deposit_by_batch.items():
            deposit_date = deposit_info["date"]
            if deposit_date.month == 4:  # April - Initial Deposit
                event_label = "Initial Deposit"
            elif deposit_date.month == 9:  # September - Top-up Deposit
                event_label = "Top-up Deposit"
            elif deposit_date.month == 10:  # October - Top-up Deposit
                event_label = "Top-up Deposit"
            else:
                event_label = f"Deposit - {deposit_date.strftime('%B')}"

            # ✅ DECIMAL PRECISION FIX: Round deposit amount to 2 decimal places
            deposit_amount = round(deposit_info["amount"], 2)

            statements.append({
                "type": "DEPOSIT",
                "batch_id": batch_id,
                "batch_name": batch_names.get(batch_id, "Unknown") if batch_id is not None else None,
                "date": deposit_info["date"].isoformat(),
                "label": event_label,
                "fund_name": deposit_info["fund_name"],
                "deposits": deposit_amount,
                "opening_balance": 0.0,  # Will be calculated in running balance phase
                "withdrawals": 0.0,
                "profit": 0.0,
                "end_balance": 0.0,  # Will be calculated
                "performance_rate": 0.0,
                "sort_priority": -1  # Deposits first in chronological order
            })
        
        # === ADD LEDGER ENTRIES (MONTHLY REPORTS) ===
        for entry in ledger_entries:
            # ✅ DECIMAL PRECISION FIX: Round all values to 2 decimal places
            opening_balance = round(float(entry.start_balance), 2)
            withdrawals_amt = round(float(entry.withdrawals), 2)
            profit_amt = round(float(entry.profit), 2)
            end_balance_amt = round(float(entry.end_balance), 2)
            
            statements.append({
                "type": "MONTHLY_REPORT",
                "date": entry.epoch_end.isoformat(),
                "label": entry.epoch_end.strftime("%B %Y"),
                "fund_name": entry.fund_name,
                "opening_balance": opening_balance,
                "deposits": 0.0,  # Ledger entries don't have separate deposit field
                "withdrawals": withdrawals_amt,
                "profit": profit_amt,
                "end_balance": end_balance_amt,
                "performance_rate": round(float(entry.performance_rate * 100), 4) if entry.performance_rate else 0.0,
                "sort_priority": 0  # Reports second
            })
            
        # === ADD WITHDRAWAL EVENTS ===
        for wd in withdrawals:
            # ✅ DECIMAL PRECISION FIX: Round withdrawal amount to 2 decimal places
            withdrawal_amount = round(float(wd.amount), 2)
            
            statements.append({
                "type": "WITHDRAWAL",
                "date": wd.date_withdrawn.isoformat() if wd.date_withdrawn else "1970-01-01T00:00:00",
                "label": f"Withdrawal - {wd.fund_name or 'Portfolio'}",
                "fund_name": wd.fund_name,
                "opening_balance": 0.0,  # Will be calculated
                "deposits": 0.0,
                "withdrawals": withdrawal_amount,
                "profit": 0.0,
                "end_balance": 0.0,  # Will be calculated
                "performance_rate": 0.0,
                "withdrawal_id": wd.id,
                "sort_priority": 1  # Withdrawals third
            })
        
        # 2. Sort chronologically for running balance calculation
        # Use (date, sort_priority) to ensure stable ordering
        statements.sort(key=lambda x: (x["date"], x["sort_priority"]))
        
        # 3. Calculate Running Balances with Sequential Enforcement
        # ✅ CRITICAL FIX: Enforce strict sequential: opening[N] = closing[N-1]
        running_balance = 0.0
        
        for i, stmt in enumerate(statements):
            if stmt["type"] == "DEPOSIT":
                # DEPOSIT: opening = current running balance
                stmt["opening_balance"] = round(running_balance, 2)
                running_balance = round(running_balance + stmt["deposits"], 2)
                stmt["end_balance"] = round(running_balance, 2)
            elif stmt["type"] == "MONTHLY_REPORT":
                # MONTHLY_REPORT: opening MUST match running_balance to maintain sequence
                stmt["opening_balance"] = round(running_balance, 2)
                # Recalculate profit based on corrected opening: profit = opening * (perf_rate / 100)
                profit_calculated = round(stmt["opening_balance"] * (stmt["performance_rate"] / 100), 2) if stmt["performance_rate"] else 0.0
                stmt["profit"] = profit_calculated
                # Closing = opening +/- deposits/withdrawals + profit
                stmt["end_balance"] = round(
                    stmt["opening_balance"] + stmt["deposits"] - stmt["withdrawals"] + stmt["profit"],
                    2
                )
                running_balance = round(stmt["end_balance"], 2)
            elif stmt["type"] == "WITHDRAWAL":
                # WITHDRAWAL: opening = current running balance
                stmt["opening_balance"] = round(running_balance, 2)
                running_balance = round(running_balance - stmt["withdrawals"], 2)
                stmt["end_balance"] = round(running_balance, 2)
        
        # 4. Sort reverse-chronological for display (newest first)
        statements.sort(key=lambda x: (x["date"], x["sort_priority"]), reverse=True)
        
        return make_response(jsonify({
            "status": 200,
            "message": "Investor statements retrieved",
            "data": statements
        }), 200)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return make_response(jsonify({
            "status": 500, 
            "message": f"Server Error: {str(e)}",
            "traceback": error_trace
        }), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/withdrawals/<int:withdrawal_id>/pdf', methods=['GET'])
@jwt_required()
def get_withdrawal_pdf(client_code, withdrawal_id):
    """
    Generate a detailed Withdrawal Statement & Receipt PDF with account reconciliation.
    """
    try:
        w = db.session.query(Withdrawal).filter(
            Withdrawal.id == withdrawal_id,
            Withdrawal.internal_client_code == client_code
        ).first()
        
        if not w:
            return make_response(jsonify({"status": 404, "message": "Withdrawal record not found"}), 404)
            
        # Get investor info
        inv = db.session.query(Investment).filter(Investment.internal_client_code == client_code).first()
        investor_name = inv.investor_name if inv else "Investor"
        
        # Get fund info and current balance
        fund_name = w.fund_name or "Portfolio"
        # Find the epoch that contains the withdrawal date
        withdrawal_epoch = db.session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == client_code,
            EpochLedger.fund_name == fund_name,
            EpochLedger.epoch_start <= w.date_withdrawn,
            EpochLedger.epoch_end >= w.date_withdrawn
        ).first()
        
        if withdrawal_epoch:
            pre_withdrawal_balance = float(withdrawal_epoch.start_balance) + float(withdrawal_epoch.deposits)
            post_withdrawal_balance = float(withdrawal_epoch.end_balance)
        else:
            # Fallback to latest valuation
            latest_valuation = db.session.query(EpochLedger).filter(
                EpochLedger.internal_client_code == client_code,
                EpochLedger.fund_name == fund_name
            ).order_by(EpochLedger.epoch_end.desc()).first()
            if latest_valuation:
                pre_withdrawal_balance = float(latest_valuation.start_balance) + float(latest_valuation.deposits)
                post_withdrawal_balance = float(latest_valuation.end_balance)
            else:
                pre_withdrawal_balance = 0.0
                post_withdrawal_balance = 0.0
        
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'InvestorTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'InvestorHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        )
        section_heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            leading=13,
        )
        small_right_style = ParagraphStyle(
            'SmallRight',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
            alignment=2,
            leading=12,
        )

        # Header with logo image
        logo_path = Path(__file__).resolve().parents[2].parent / 'ofds-frontend' / 'public' / 'AIBlight.png'
        logo_flowable = None
        if logo_path.exists():
            logo_flowable = Image(str(logo_path), width=150, height=45)
            logo_flowable.hAlign = 'LEFT'

        head_office_html = (
            "<para align=right>"
            "<font size=9><b>HEAD OFFICE</b></font><br/>"
            "<font size=8>The Promenade, 5th Floor | General Mathenge Rd</font><br/>"
            "<font size=8>P.O. Box 43676-00100 | Nairobi | Kenya</font><br/>"
            "<font size=8>T: 0711047000 | M: 0790404571</font><br/>"
            "<font size=8>W: www.aib-axysafrica.com</font>"
            "</para>"
        )
        header_cells = [
            logo_flowable if logo_flowable is not None else Paragraph('<font size=18><b>AIB-AXYS Africa</b></font>', title_style),
            Paragraph(head_office_html, small_right_style)
        ]
        header_table = Table([header_cells], colWidths=[3.8 * inch, 3.7 * inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.04 * inch))
        story.append(Table([['']], colWidths=[7.5 * inch], style=[('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#00005b'))]))
        story.append(Spacer(1, 0.14 * inch))
        
        # Header (Logo)
        logo_path = Path(__file__).resolve().parents[2].parent / 'ofds-frontend' / 'public' / 'AIBlight.png'
        if logo_path.exists():
            logo = Image(str(logo_path), width=150, height=45)
            logo.hAlign = 'LEFT'
            story.append(logo)
        else:
            story.append(Paragraph('AIB-AXYS Africa', title_style))
            
        story.append(Spacer(1, 0.15 * inch))
        story.append(Table([['']], colWidths=[7.5 * inch], style=[('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#00005b'))]))
        story.append(Spacer(1, 0.2 * inch))
        
        story.append(Paragraph('WITHDRAWAL STATEMENT & AUTHORIZATION RECEIPT', heading_style))
        story.append(Spacer(1, 0.15 * inch))
        
        # Withdrawal Details - detailed table
        withdrawal_date_str = w.date_withdrawn.strftime("%B %d, %Y") if w.date_withdrawn else "N/A"
        approved_date_str = w.approved_at.strftime("%B %d, %Y") if w.approved_at else "Pending"
        receipt_data = [
            ['Reference ID', f': WDR-{w.id}', 'Withdrawal Date', f': {withdrawal_date_str}'],
            ['Client Code', f': {client_code}', 'Client Name', f': {investor_name}'],
            ['Fund / Investment', f': {fund_name}', 'Status', f': {w.status}'],
            ['Approved Date', f': {approved_date_str}', '', ''],
        ]
        receipt_table = Table(receipt_data, colWidths=[1.2 * inch, 1.7 * inch, 1.2 * inch, 3.4 * inch])
        receipt_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),
        ]))
        story.append(Paragraph('Withdrawal Details', section_heading_style))
        story.append(receipt_table)
        story.append(Spacer(1, 0.25 * inch))
        
        # Amount Box - highlighted
        amount_data = [
            ['WITHDRAWAL AMOUNT', f'USD {float(w.amount):,.2f}']
        ]
        amount_table = Table(amount_data, colWidths=[3.5 * inch, 3.5 * inch])
        amount_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica-Bold', 18),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#00005b')),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#00005b')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
            ('TOPPADDING', (0, 0), (-1, -1), 18),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ]))
        story.append(amount_table)
        story.append(Spacer(1, 0.25 * inch))
        
        # Account Reconciliation
        reconciliation_data = [
            ['Pre-Withdrawal Balance', f'${pre_withdrawal_balance:,.2f}'],
            ['Withdrawal Amount', f'(${float(w.amount):,.2f})'],
            ['Post-Withdrawal Balance', f'${post_withdrawal_balance:,.2f}'],
        ]
        
        reconciliation_table = Table(reconciliation_data, colWidths=[5.2 * inch, 2.3 * inch])
        reconciliation_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(Paragraph('Account Reconciliation (USD)', section_heading_style))
        story.append(reconciliation_table)
        story.append(Spacer(1, 0.2 * inch))
        
        # Transaction details
        details_style = ParagraphStyle(
            'Details',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            leading=11,
        )
        details_text = (
            f"<b>Authorization & Confirmation:</b> This statement confirms that a withdrawal of USD {float(w.amount):,.2f} "
            f"has been processed for {investor_name} ({client_code}) from the {fund_name} investment. "
            f"The withdrawal has been authorized with status: <b>{w.status}</b>. "
            f"The funds will be transferred according to the withdrawal processing timeline. "
            f"Your account balance reflects the post-withdrawal amount."
        )
        story.append(Paragraph(details_text, details_style))
        story.append(Spacer(1, 0.15 * inch))
        
        # Important notice
        notice_style = ParagraphStyle(
            'Notice',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#d32f2f'),
            leading=10,
            leftIndent=5,
        )
        story.append(Paragraph(
            '<b>⚠ Important:</b> This withdrawal is subject to fund rules, terms and conditions. '
            'Processing times may vary. Please contact our office for details on settlement timing.',
            notice_style
        ))
        story.append(Spacer(1, 0.15 * inch))
        
        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#999999'),
            leading=10,
        )
        story.append(Paragraph(
            '<b>Disclaimer & Notice:</b> This is an electronically generated withdrawal authorization receipt. '
            'No signature is required. This statement is provided for informational purposes and confirms your withdrawal request. '
            'All figures are subject to verification and may not reflect real-time data. Withdrawal completion is subject to fund rules and processing timelines.',
            footer_style
        ))
        story.append(Paragraph(
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | "
            f"Withdrawal ID: {w.id} | Client Code: {client_code}",
            footer_style
        ))
        
        doc.build(story)
        pdf_buffer.seek(0)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"withdrawal-receipt-{client_code}-{w.id}.pdf"
        )
    except Exception as e:
        import traceback
        print(f"❌ Withdrawal PDF generation error for {client_code}, withdrawal {withdrawal_id}: {str(e)}")
        print(traceback.format_exc())
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/deposits/<int:batch_id>/pdf', methods=['GET'])
@jwt_required()
def get_deposit_receipt_pdf(client_code, batch_id):
    """
    Generate a branded Deposit Statement/Receipt PDF.
    Shows detailed deposit information and account reconciliation.
    """
    try:
        # Get all investments for this client in this batch
        investments = db.session.query(Investment).filter(
            Investment.internal_client_code == client_code,
            Investment.batch_id == batch_id
        ).all()
        
        if not investments:
            return make_response(jsonify({"status": 404, "message": "Deposit record not found"}), 404)
        
        # Aggregate investment data
        inv_first = investments[0]  # Get first for metadata
        total_amount_deposited = sum(float(inv.amount_deposited) for inv in investments)
        deposit_date = inv_first.date_deposited
        investor_name = inv_first.investor_name
        
        # Get batch info
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        batch_name = batch.batch_name if batch else "Unknown Batch"
        
        # Get fund info (use first investment's fund)
        fund_name = inv_first.fund_name or (inv_first.fund.fund_name if inv_first.fund else "Portfolio")
        
        # Get current holding/valuation for this investor/fund
        latest_valuation = db.session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == client_code,
            EpochLedger.fund_name == fund_name
        ).order_by(EpochLedger.epoch_end.desc()).first()
        
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'InvestorTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'InvestorHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        )
        section_heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            leading=13,
        )
        small_right_style = ParagraphStyle(
            'SmallRight',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
            alignment=2,
            leading=12,
        )

        # Header with logo image
        logo_path = Path(__file__).resolve().parents[2].parent / 'ofds-frontend' / 'public' / 'AIBlight.png'
        logo_flowable = None
        if logo_path.exists():
            logo_flowable = Image(str(logo_path), width=150, height=45)
            logo_flowable.hAlign = 'LEFT'

        head_office_html = (
            "<para align=right>"
            "<font size=9><b>HEAD OFFICE</b></font><br/>"
            "<font size=8>The Promenade, 5th Floor | General Mathenge Rd</font><br/>"
            "<font size=8>P.O. Box 43676-00100 | Nairobi | Kenya</font><br/>"
            "<font size=8>T: 0711047000 | M: 0790404571</font><br/>"
            "<font size=8>W: www.aib-axysafrica.com</font>"
            "</para>"
        )
        header_cells = [
            logo_flowable if logo_flowable is not None else Paragraph('<font size=18><b>AIB-AXYS Africa</b></font>', title_style),
            Paragraph(head_office_html, small_right_style)
        ]
        header_table = Table([header_cells], colWidths=[3.8 * inch, 3.7 * inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.04 * inch))
        story.append(Table([['']], colWidths=[7.5 * inch], style=[('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#00005b'))]))
        story.append(Spacer(1, 0.14 * inch))
        story.append(Paragraph('DEPOSIT STATEMENT & CONFIRMATION', heading_style))
        story.append(Spacer(1, 0.15 * inch))
        
        # Deposit details section
        deposit_date_str = inv_first.date_deposited.strftime("%B %d, %Y") if inv_first.date_deposited else "N/A"
        receipt_data = [
            ['Reference ID', f': DEP-{batch_id}-{inv_first.id}', 'Deposit Date', f': {deposit_date_str}'],
            ['Client Code', f': {client_code}', 'Client Name', f': {inv_first.investor_name}'],
            ['Batch', f': {batch_name}', 'Fund', f': {fund_name}'],
        ]
        
        receipt_table = Table(receipt_data, colWidths=[1.2 * inch, 1.7 * inch, 1.2 * inch, 3.4 * inch])
        receipt_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),
        ]))
        story.append(Paragraph('Deposit Details', section_heading_style))
        story.append(receipt_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Amount deposited - highlighted box
        amount_data = [
            ['AMOUNT DEPOSITED', f'USD {total_amount_deposited:,.2f}']
        ]
        amount_table = Table(amount_data, colWidths=[3.5 * inch, 3.5 * inch])
        amount_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica-Bold', 16),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#00005b')),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#00005b')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
            ('TOPPADDING', (0, 0), (-1, -1), 18),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ]))
        story.append(amount_table)
        story.append(Spacer(1, 0.25 * inch))
        
        # Account reconciliation
        valuation_at_deposit = db.session.query(EpochLedger).filter(
            EpochLedger.internal_client_code == client_code,
            EpochLedger.fund_name == fund_name,
            EpochLedger.epoch_start <= deposit_date,
            EpochLedger.epoch_end >= deposit_date
        ).order_by(EpochLedger.epoch_end.desc()).first()

        if valuation_at_deposit:
            opening_balance_calc = float(valuation_at_deposit.start_balance)
        else:
            previous_epoch = db.session.query(EpochLedger).filter(
                EpochLedger.internal_client_code == client_code,
                EpochLedger.fund_name == fund_name,
                EpochLedger.epoch_end < deposit_date
            ).order_by(EpochLedger.epoch_end.desc()).first()
            opening_balance_calc = float(previous_epoch.end_balance) if previous_epoch else 0.0

        deposits_total = total_amount_deposited
        withdrawals_total = 0.0
        profit = 0.0
        current_balance = opening_balance_calc + deposits_total

        reconciliation_data = [
            ['Opening Balance', f'${opening_balance_calc:,.2f}'],
            ['Deposits This Period', f'${deposits_total:,.2f}'],
            ['Withdrawals This Period', f'(${withdrawals_total:,.2f})'],
            ['Performance / Profit', f'${profit:,.2f}'],
            ['Current Account Balance', f'${current_balance:,.2f}'],
        ]
        
        reconciliation_table = Table(reconciliation_data, colWidths=[5.2 * inch, 2.3 * inch])
        reconciliation_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(Paragraph('Account Reconciliation (USD)', section_heading_style))
        story.append(reconciliation_table)
        story.append(Spacer(1, 0.2 * inch))
        
        # Details section
        details_style = ParagraphStyle(
            'Details',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            leading=11,
            leftIndent=0
        )
        details_text = (
            f"<b>Deposit Confirmation:</b> This statement confirms that USD {total_amount_deposited:,.2f} "
            f"was received for {investor_name} ({client_code}) into the {fund_name} fund as part of "
            f"<b>{batch_name}</b>. The deposit has been processed and allocated to your investment account. "
            f"Your current account balance reflects this deposit, withdrawals, and applicable performance gains/losses. "
            f"All figures are in United States Dollars (USD) unless otherwise noted."
        )
        story.append(Paragraph(details_text, details_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#999999'),
            leading=10,
        )
        story.append(Paragraph(
            '<b>Disclaimer:</b> This is an electronically generated deposit confirmation. '
            'No signature is required. This statement is provided for informational purposes only. '
            'All figures are subject to verification and may not reflect real-time data.',
            footer_style
        ))
        story.append(Paragraph(
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | "
            f"Batch ID: {batch_id} | Investment ID: {inv_first.id}",
            footer_style
        ))
        
        doc.build(story)
        pdf_buffer.seek(0)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"deposit-confirmation-{client_code}-{batch_id}.pdf"
        )
    except Exception as e:
        import traceback
        print(f"❌ Deposit PDF generation error for {client_code}, batch {batch_id}: {str(e)}")
        print(traceback.format_exc())
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>', methods=['PATCH'])
@jwt_required()
def update_investor_profile(client_code):
    """
    Update investor identity fields globally (propagates across all investments for that client_code).
    Body supports: investor_name, investor_email, investor_phone
    """
    try:
        data = request.get_json() or {}
        session = db.session

        q = session.query(Investment).filter(Investment.internal_client_code == client_code)
        existing = q.first()
        if not existing:
            return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)

        updates = {}
        for field in ("investor_name", "investor_email", "investor_phone"):
            if field in data and data[field] is not None:
                updates[field] = data[field]

        # Extra fields propagated to all investment rows
        extra_fields = {}
        for field in ("wealth_manager", "IFA", "contract_note", "valuation"):
            if field in data and data[field] is not None:
                extra_fields[field] = data[field]

        if not updates and not extra_fields:
            return make_response(jsonify({"status": 400, "message": "No updatable fields provided"}), 400)

        if updates:
            q.update(updates, synchronize_session=False)
        if extra_fields:
            q.update(extra_fields, synchronize_session=False)
        session.commit()

        return make_response(jsonify({"status": 200, "message": "Investor updated", "data": {"client_code": client_code, **updates, **extra_fields}}), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/withdrawals', methods=['GET'])
@jwt_required()
def get_investor_withdrawals(client_code):
    """
    Get all withdrawal requests for a specific investor (client_code).
    Returns withdrawal history with status and amounts.
    """
    try:
        from app.Investments.model import Withdrawal
        
        # Verify investor exists
        investor = db.session.query(Investment).filter(
            Investment.internal_client_code == client_code
        ).first()
        
        if not investor:
            return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)
        
        # Get all withdrawals for this investor
        withdrawals = db.session.query(Withdrawal).filter(
            Withdrawal.internal_client_code == client_code
        ).order_by(Withdrawal.created_at.desc()).all()
        
        withdrawal_data = []
        for w in withdrawals:
            withdrawal_data.append({
                "id": w.id,
                "amount": float(w.amount),
                "fund_id": w.fund_id,
                "status": w.status,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "approved_at": w.approved_at.isoformat() if hasattr(w, 'approved_at') and w.approved_at else None,
                "paid_at": w.paid_at.isoformat() if hasattr(w, 'paid_at') and w.paid_at else None,
            })
        
        return make_response(jsonify({
            "status": 200,
            "message": "Investor withdrawals retrieved",
            "client_code": client_code,
            "total_count": len(withdrawal_data),
            "withdrawals": withdrawal_data
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ==================== WITHDRAWALS ====================

@investment_v1.route('/api/v1/withdrawals', methods=['POST'])
@jwt_required()
def create_withdrawal():
    """
    Create a withdrawal request.
    Body: { client_id, amount, fund_id, status } where status defaults Pending.
    client_id == internal_client_code
    """
    try:
        data = request.get_json(silent=True) or {}

        # Support investor_id (investment PK) as alternative to client_id
        investor_id = data.get('investor_id')
        client_id = (data.get('client_id') or '').strip()

        if investor_id and not client_id:
            inv_row = db.session.query(Investment).filter(Investment.id == investor_id).first()
            if not inv_row:
                return make_response(jsonify({"status": 404, "message": "Investment not found"}), 404)
            client_id = inv_row.internal_client_code

        if not client_id:
            return make_response(jsonify({"status": 400, "message": "client_id or investor_id is required"}), 400)

        # fund_id is optional — derive from investor's existing investment if omitted
        fund_id = data.get('fund_id')
        fund_name = None
        if fund_id is not None:
            fund_id = int(fund_id)
            core = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
            if not core:
                return make_response(jsonify({"status": 404, "message": "Core fund not found"}), 404)
            fund_name = core.fund_name
        else:
            # Try to derive from investor's investment
            inv_row = db.session.query(Investment).filter(
                Investment.internal_client_code == client_id
            ).first()
            if inv_row and inv_row.fund_id:
                fund_id = inv_row.fund_id
                core = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
                fund_name = core.fund_name if core else None

        amount = data.get('amount')
        if amount is None:
            return make_response(jsonify({"status": 400, "message": "amount is required"}), 400)
        
        # Validate amount is positive
        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                return make_response(jsonify({"status": 400, "message": "amount must be greater than 0"}), 400)
        except (ValueError, TypeError):
            return make_response(jsonify({"status": 400, "message": "amount must be a valid number"}), 400)

        status = normalize_withdrawal_status(data.get('status'))

        w = Withdrawal(
            internal_client_code=client_id,
            fund_id=fund_id,
            fund_name=fund_name,
            amount=amount,
            status=status,
            approved_at=datetime.now(timezone.utc) if status == 'Approved' else None,
        )
        db.session.add(w)
        db.session.commit()

        return make_response(jsonify({"status": 201, "message": "Withdrawal created", "data": {"id": w.id}}), 201)
    except IntegrityError as ie:
        db.session.rollback()
        return make_response(jsonify({"status": 409, "message": str(ie.orig)}), 409)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/withdrawals', methods=['GET'])
@jwt_required()
def list_withdrawals():
    """
    List withdrawals with optional filters:
    - status=Pending|Approved|Rejected
    Returns withdrawal data with fund information from relationship
    """
    try:
        status = request.args.get('status')
        q = db.session.query(Withdrawal).order_by(Withdrawal.date_withdrawn.desc())
        if status:
            status = normalize_withdrawal_status(status)
            q = q.filter(Withdrawal.status == status)
        rows = q.all()
        data = [
            {
                "id": w.id,
                "client_id": w.internal_client_code,
                "fund_id": w.fund_id,
                "fund_name": w.fund.fund_name if w.fund else w.fund_name,  # Use relationship if available, fallback to column
                "amount": float(w.amount),
                "status": w.status,
                "date_withdrawn": w.date_withdrawn.isoformat(),
                "approved_at": w.approved_at.isoformat() if w.approved_at else None,
                "note": w.note,
            }
            for w in rows
        ]
        return make_response(jsonify({
            "status": 200,
            "data": data,
            "message": f"Retrieved {len(data)} withdrawal(s)"
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/withdrawals/upload', methods=['POST'])
@jwt_required()
def upload_withdrawals():
    """Upload withdrawals via Excel/CSV.

    Expected columns (case-insensitive):
      REQUIRED:
      - internal_client_code
      - amount
      - fund_name
      - date_withdrawn
      
      OPTIONAL:
      - investor_name (reference only)
      - status (defaults to 'Approved' - uploaded withdrawals are ready for valuation immediately)
      - note

    The endpoint creates/updates Withdrawal rows.
    Uploaded withdrawals are marked as 'Approved' by default, making them immediately
    available in valuation preview calculations.
    """
    try:
        if 'file' not in request.files:
            return make_response(jsonify({"status": 400, "message": "Missing file upload"}), 400)
        file = request.files.get('file')
        if not file or file.filename == '':
            return make_response(jsonify({"status": 400, "message": "No file provided"}), 400)

        import pandas as pd
        from io import BytesIO

        file_stream = BytesIO(file.read())

        # Try to read as Excel first, then CSV
        try:
            if file.filename.lower().endswith('.csv'):
                df = pd.read_csv(file_stream)
            else:
                df = pd.read_excel(file_stream)
        except Exception as e:
            return make_response(jsonify({"status": 400, "message": f"Error reading file: {str(e)}"}), 400)

        # Normalize column names
        df.columns = df.columns.str.lower().str.strip()

        # Column mapping - support both old and new names
        column_mapping = {
            'internal_client_code': 'internal_client_code',
            'amount(usd)': 'amount',
            'amount': 'amount',
            'fund_name': 'fund_name',
            'date_transferred': 'date_withdrawn',
            'date_withdrawn': 'date_withdrawn',
            'investor_name': 'investor_name',
            'status': 'status',
            'note': 'note',
        }
        
        # Apply mapping only for columns that exist
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        # Required columns
        required_columns = ['internal_client_code', 'amount', 'fund_name', 'date_withdrawn']
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            return make_response(jsonify({"status": 400, "message": f"Missing required columns: {', '.join(missing)}"}), 400)

        # Drop rows with missing required data
        df = df.dropna(subset=required_columns)

        created = 0
        updated = 0
        errors = []

        for idx, row in df.iterrows():
            prev_created = created
            try:
                # Required fields
                internal_code = str(row['internal_client_code']).strip()
                fund_name = str(row['fund_name']).strip()
                amount = Decimal(str(row['amount']))
                date_withdrawn = row['date_withdrawn']
                
                # Parse date if string
                if isinstance(date_withdrawn, str):
                    # Try multiple date formats
                    for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                        try:
                            date_withdrawn = datetime.strptime(date_withdrawn, date_format)
                            break
                        except ValueError:
                            continue
                    else:
                        raise ValueError(f"Invalid date format: {date_withdrawn}")
                
                # Convert pandas Timestamp to datetime if needed
                if hasattr(date_withdrawn, 'to_pydatetime'):
                    date_withdrawn = date_withdrawn.to_pydatetime()

                # Ensure withdrawal timestamps are UTC-aware for reliable filtering and comparisons
                if date_withdrawn.tzinfo is None:
                    date_withdrawn = date_withdrawn.replace(tzinfo=timezone.utc)
                else:
                    date_withdrawn = date_withdrawn.astimezone(timezone.utc)

                # Optional fields
                investor_name = str(row.get('investor_name', '')).strip() if 'investor_name' in row else ''
                # DEFAULT: Uploaded withdrawals are considered 'Approved' (ready for valuation preview)
                # If the Excel file includes a status column, that takes precedence
                status = str(row.get('status', 'Approved')).strip()
                status = normalize_withdrawal_status(status)
                note = str(row.get('note', '')).strip() if 'note' in row else None

                # Determine core fund
                core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == fund_name.lower()).first()
                if not core:
                    raise ValueError(f"Fund '{fund_name}' not found")

                # Attempt to find an existing withdrawal for this investor+fund+date
                existing = db.session.query(Withdrawal).filter(
                    Withdrawal.internal_client_code == internal_code,
                    Withdrawal.fund_id == core.id,
                    Withdrawal.date_withdrawn == date_withdrawn,
                ).first()

                if existing:
                    # Update existing withdrawal
                    existing.amount = amount
                    existing.status = status
                    if status == 'Approved':
                        existing.approved_at = datetime.now(timezone.utc)
                    existing.note = note
                    updated += 1
                else:
                    # Create new withdrawal
                    w = Withdrawal(
                        internal_client_code=internal_code,
                        fund_id=core.id,
                        fund_name=core.fund_name,
                        amount=amount,
                        date_withdrawn=date_withdrawn,
                        status=status,
                        note=note,
                    )
                    
                    # Link to a batch if we can infer it from an investment
                    inv = db.session.query(Investment).filter(
                        Investment.internal_client_code == internal_code,
                        Investment.fund_id == core.id,
                    ).order_by(Investment.id.desc()).first()
                    if inv:
                        w.batch_id = inv.batch_id
                    
                    # Set approved_at if status is Approved
                    if status == 'Approved':
                        w.approved_at = datetime.now(timezone.utc)

                    db.session.add(w)
                    created += 1
                    
                # Trigger email if new and we have investor info
                if created > prev_created:
                    from app.utils.email_service import EmailService
                    # We already have internal_code, amount, fund_name
                    # Get email from latest investment record
                    inv = db.session.query(Investment).filter(
                        Investment.internal_client_code == internal_code
                    ).order_by(Investment.id.desc()).first()
                    
                    if inv and inv.investor_email:
                        EmailService.send_withdrawal_received_email(
                            client_code=internal_code,
                            investor_name=inv.investor_name or "Investor",
                            investor_email=inv.investor_email,
                            amount=amount,
                            fund_name=fund_name,
                            trigger_source="withdrawals.upload.big_four_event",
                        )

            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")

        db.session.commit()

        return make_response(jsonify({
            "status": 201,
            "message": f"Withdrawals uploaded (created={created}, updated={updated})",
            "errors": errors,
        }), 201)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/withdrawals/<int:withdrawal_id>', methods=['PATCH'])
@jwt_required()
def update_withdrawal(withdrawal_id: int):
    """
    Approve/Reject a withdrawal.
    On approval: Triggers calculations, locks the withdrawal, and records event.
    
    Body: { status: 'Approved'|'Rejected', note?: string }
    """
    try:
        data = request.get_json() or {}
        status = (data.get('status') or '').strip().capitalize()
        if status not in ('Approved', 'Rejected'):
            return make_response(jsonify({"status": 400, "message": "status must be Approved or Rejected"}), 400)

        w = db.session.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
        if not w:
            return make_response(jsonify({"status": 404, "message": "Withdrawal not found"}), 404)

        # Prevent duplicate approval
        if w.status == 'Approved' and status == 'Approved':
            return make_response(jsonify({"status": 400, "message": "Withdrawal already approved"}), 400)

        old_status = w.status
        w.status = status
        note = data.get('note', '').strip()
        if note:
            w.note = note
        
        # Set approval timestamp only when transitioning to Approved
        if status == 'Approved':
            w.approved_at = datetime.now(timezone.utc)
            
            # Trigger calculations: Update investor valuation/balance
            try:
                _calculate_investor_impact(w)
                message = f"Withdrawal approved and calculations updated"
                
                # Email trigger intentionally disabled here.
                # Allowed trigger is withdrawals upload only.
            except Exception as calc_err:
                # Log but don't fail the approval
                print(f"⚠️  Warning: Calculation failed for withdrawal {withdrawal_id}: {str(calc_err)}")
                message = f"Withdrawal approved (calculation warning: {str(calc_err)})"
        else:
            w.approved_at = None
            message = "Withdrawal rejected"

        # Log event for audit trail
        _log_withdrawal_event(withdrawal_id, old_status, status, note)
        
        db.session.commit()
        return make_response(jsonify({
            "status": 200, 
            "message": message,
            "data": {
                "id": w.id,
                "status": w.status,
                "approved_at": w.approved_at.isoformat() if w.approved_at else None
            }
        }), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _calculate_investor_impact(withdrawal: Withdrawal):
    """
    Calculate impact of approved withdrawal on investor valuation.
    Updates balances and records in audit logs.
    """
    from app.utils.audit_log import create_audit_log
    
    client_code = withdrawal.internal_client_code
    fund = withdrawal.fund
    amount = withdrawal.amount
    
    # Get latest valuation for this investor/fund
    latest_investment = (
        db.session.query(Investment)
        .filter(
            Investment.internal_client_code == client_code,
            Investment.fund_id == fund.id if fund else Investment.fund_name == withdrawal.fund_name
        )
        .order_by(Investment.date_deposited.desc())
        .first()
    )
    
    if latest_investment:
        old_valuation = latest_investment.valuation
        # Update valuation (deduct withdrawal from current valuation)
        if latest_investment.valuation:
            latest_investment.valuation = max(Decimal('0'), Decimal(str(latest_investment.valuation)) - amount)
            
        # Let the NEXT EpochLedger naturally acquire this withdrawal during its own valuation run.
        # This perfectly preserves Snapshot Isolation for committed reports.
        
        # Log to audit trail
        create_audit_log(
            action="WITHDRAWAL_APPROVED",
            target_type="Withdrawal",
            target_id=withdrawal.id,
            target_name=f"{client_code} - {withdrawal.fund_name}",
            description=f"AUM updated: ${amount} withdrawal processed for client {client_code}",
            old_value={
                "client_code": client_code,
                "fund_name": withdrawal.fund_name,
                "amount": float(amount),
                "valuation_before": float(old_valuation) if old_valuation else None,
            },
            new_value={
                "client_code": client_code,
                "fund_name": withdrawal.fund_name,
                "amount": float(amount),
                "valuation_after": float(latest_investment.valuation),
            },
            success=True
        )
        
        db.session.commit()
    
    print(f"✅ Withdrawal #{withdrawal.id} approved for {client_code} in {withdrawal.fund_name}: ${amount}")


def _log_withdrawal_event(withdrawal_id: int, old_status: str, new_status: str, note: str = ""):
    """
    Log withdrawal status change to audit trail.
    """
    from app.utils.audit_log import create_audit_log
    
    create_audit_log(
        action="WITHDRAWAL_STATUS_CHANGE",
        target_type="Withdrawal",
        target_id=withdrawal_id,
        description=f"Status changed from {old_status} to {new_status}",
        old_value={"status": old_status, "note": note},
        new_value={"status": new_status, "note": note},
        success=True
    )


# ============================================================
# PENDING EMAIL ENDPOINTS — Manual Confirmation Gate
# ============================================================

@investment_v1.route('/api/v1/emails/pending', methods=['GET'])
@jwt_required()
def list_pending_emails():
    """
    List all emails awaiting manual admin confirmation.
    Returns every PendingEmail with status='Pending_Confirmation'.

    Response shape:
    {
        "status": 200,
        "count": 3,
        "data": [
            {
                "id": 1,
                "email_type": "DEPOSIT_CONFIRMATION",
                "recipient_email": "investor@example.com",
                "recipient_name": "John Doe",
                "subject": "Deposit Received - Batch 1",
                "batch_name": "Batch 1",
                "fund_name": null,
                "amount": 50000.00,
                "batch_id": 1,
                "investor_id": 12,
                "created_at": "2026-04-08T06:00:00+00:00"
            }
        ]
    }
    """
    try:
        from app.Investments.model import PendingEmail
        rows = (
            db.session.query(PendingEmail)
            .filter(PendingEmail.status == 'Pending_Confirmation')
            .order_by(PendingEmail.created_at.asc())
            .all()
        )
        data = [
            {
                "id": r.id,
                "email_type": r.email_type,
                "recipient_email": r.recipient_email,
                "recipient_name": r.recipient_name,
                "subject": r.subject,
                "body": r.body,
                "batch_name": r.batch_name,
                "fund_name": r.fund_name,
                "amount": float(r.amount) if r.amount is not None else None,
                "batch_id": r.batch_id,
                "investor_id": r.investor_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return make_response(jsonify({"status": 200, "count": len(data), "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/<int:email_id>/confirm', methods=['POST'])
@jwt_required()
def confirm_pending_email(email_id):
    """
    Confirm and send a pending email via Office365 / configured SMTP.
    Sets status='Confirmed', logs to EmailLog, and fires the SMTP send.

    Response:
    { "status": 200, "message": "Email sent and confirmed." }
    """
    try:
        from app.Investments.model import PendingEmail, EmailLog
        from app.utils.email_service import EmailService
        from flask_mail import Message
        from app.utils.email_service import mail

        pending = db.session.get(PendingEmail, email_id)
        if not pending:
            return make_response(jsonify({"status": 404, "message": "Pending email not found"}), 404)

        if pending.status != 'Pending_Confirmation':
            return make_response(jsonify({
                "status": 409,
                "message": f"Email is already in state '{pending.status}' and cannot be resent."
            }), 409)

        # ── Send via SMTP ──
        try:
            msg = Message(
                subject=pending.subject,
                recipients=[pending.recipient_email],
                bcc=[EmailService.BCC_EMAIL],
                body=pending.body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER', EmailService.BCC_EMAIL)
            )
            mail.send(msg)
            send_ok = True
        except Exception as smtp_err:
            logger.error(f"SMTP send failed for pending email {email_id}: {smtp_err}")
            send_ok = False

        # ── Update PendingEmail record ──
        pending.status = 'Confirmed' if send_ok else 'Failed'
        pending.processed_at = datetime.now(timezone.utc)
        db.session.flush()

        # ── Write to EmailLog audit trail ──
        log_row = EmailLog(
            investor_id=pending.investor_id,
            batch_id=pending.batch_id,
            status='Sent' if send_ok else 'Failed',
            email_type=pending.email_type,
            recipient_count=1,
            success_count=1 if send_ok else 0,
            failure_count=0 if send_ok else 1,
            error_message=None if send_ok else 'SMTP delivery failed',
            trigger_source=pending.trigger_source or 'emails.confirm_pending_email',
        )
        db.session.add(log_row)
        db.session.commit()

        if send_ok:
            logger.info(f"Pending email {email_id} confirmed and sent to {pending.recipient_email}")
            return make_response(jsonify({"status": 200, "message": "Email sent and confirmed."}), 200)
        else:
            return make_response(jsonify({"status": 502, "message": "SMTP send failed. Record marked as Failed."}), 502)

    except Exception as e:
        db.session.rollback()
        logger.error(f"confirm_pending_email error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/<int:email_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_pending_email(email_id):
    """
    Cancel (suppress) a pending email — marks it 'Suppressed' without sending.

    Response:
    { "status": 200, "message": "Email suppressed." }
    """
    try:
        from app.Investments.model import PendingEmail

        pending = db.session.get(PendingEmail, email_id)
        if not pending:
            return make_response(jsonify({"status": 404, "message": "Pending email not found"}), 404)

        if pending.status != 'Pending_Confirmation':
            return make_response(jsonify({
                "status": 409,
                "message": f"Email is already in state '{pending.status}'."
            }), 409)

        pending.status = 'Suppressed'
        pending.processed_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(f"Pending email {email_id} suppressed for {pending.recipient_email}")
        return make_response(jsonify({"status": 200, "message": "Email suppressed."}), 200)

    except Exception as e:
        db.session.rollback()
        logger.error(f"cancel_pending_email error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)
