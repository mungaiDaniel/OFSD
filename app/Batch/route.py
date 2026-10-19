from flask import request, Blueprint, jsonify, make_response, send_file
from flask_jwt_extended import jwt_required
from app.utils.decorators import super_admin_required
from flask_cors import cross_origin
from sqlalchemy import or_
from app.database.database import db
from app.Batch.controllers import BatchController
from app.Batch.model import Batch
from app.utils.audit_log import audit_log_file_upload
from app.database.product_type import SHARES
from app.Investments.model import EmailLog, Investment
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import csv

batch_v1 = Blueprint("batch_v1", __name__, url_prefix='/')

# PATCH /batches/<id> fields that are real edits (super_admin-only), as opposed
# to the stage-advance workflow fields sent by the Transfer/Deploy modals.
BATCH_EDIT_FIELDS = ("batch_name", "certificate_number")

# ==================== BATCH ENDPOINTS ====================

@batch_v1.route('/api/v1/batches', methods=['POST'])
@jwt_required()
def create_batch():
    """
    Create a new batch
    
    Request Body:
    {
        "batch_name": "MAR-2026-OFFSHORE",
        "certificate_number": "CERT-001",
        "date_deployed": "2026-03-01T00:00:00",
        "duration_days": 30
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
        return BatchController.create_batch(data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches', methods=['GET'])
@jwt_required()
def get_all_batches():
    """Get all batches. Optional ?product=FUNDS|SHARES filters by product type."""
    try:
        session = db.session
        product = request.args.get("product", default=None, type=str)
        if product:
            product = product.strip().upper()
        return BatchController.get_all_batches(session, product=product)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>', methods=['GET'])
@jwt_required()
def get_batch(batch_id):
    """Get a specific batch by ID"""
    try:
        session = db.session
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=200, type=int)
        search = request.args.get("search", default=None, type=str)
        show_all = (request.args.get("show_all", default="") or "").strip().lower() in ("1", "true", "yes")
        return BatchController.get_batch_by_id(batch_id, session, page=page, per_page=per_page, search=search, show_all=show_all)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/investments-light', methods=['GET'])
@jwt_required()
def get_batch_investments_light(batch_id):
    """Full per-investor list (cheap fields only) for the Transfer/Deploy modals."""
    try:
        return BatchController.get_batch_investments_light(batch_id, db.session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/shares-transfer-preview', methods=['GET'])
@jwt_required()
def preview_shares_transfer(batch_id):
    """
    Dry-run fee preview for the Transferred step of a SHARES (DPRP) batch — no
    DB writes. Query params: entry_fee_percent, total_transaction_cost_usd.
    Returns per-deposit deposit/entry_fee/balance_after_entry/transaction_cost/net,
    plus totals, for the batch UI's fee-preview table.
    """
    from app.database.product_type import SHARES
    from app.logic.shares_transfer_service import SharesTransferService, SharesTransferError
    try:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)
        if batch.product_type != SHARES:
            return make_response(jsonify({
                "status": 400,
                "message": "The transfer-fee preview only applies to SHARES batches."
            }), 400)

        entry_fee_percent = request.args.get("entry_fee_percent", default="0")
        total_transaction_cost_usd = request.args.get("total_transaction_cost_usd", default="0")

        preview = SharesTransferService.preview(
            batch, db.session, entry_fee_percent, total_transaction_cost_usd
        )
        return make_response(jsonify({"status": 200, "data": preview}), 200)
    except SharesTransferError as e:
        return make_response(jsonify({"status": 400, "message": str(e)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/shares-deployment-preview', methods=['GET'])
@jwt_required()
def preview_shares_deployment(batch_id):
    """
    Dry-run deployment preview for a SHARES (DPRP) batch — no DB writes. Query
    params: exchange_rate, price_per_share_ngn, shares_allocated. Returns per-
    deposit net_usd/net_ngn/tier1/round2/total shares/refund, plus batch
    totals and an "Oversubscribed"/"Fully subscribed" banner.
    """
    from app.database.product_type import SHARES
    from app.logic.shares_deployment_service import SharesDeploymentService, SharesDeploymentError
    try:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)
        if batch.product_type != SHARES:
            return make_response(jsonify({
                "status": 400,
                "message": "The deployment preview only applies to SHARES batches."
            }), 400)

        exchange_rate = request.args.get("exchange_rate", default="0")
        price_per_share_ngn = request.args.get("price_per_share_ngn", default="0")
        shares_allocated = request.args.get("shares_allocated", default="0")

        preview = SharesDeploymentService.preview(
            batch, db.session, exchange_rate, price_per_share_ngn, shares_allocated
        )
        return make_response(jsonify({"status": 200, "data": preview}), 200)
    except SharesDeploymentError as e:
        return make_response(jsonify({"status": 400, "message": str(e)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>', methods=['PUT'])
@jwt_required()
@super_admin_required
def update_batch(batch_id):
    """
    Update a batch
    
    Request Body (optional fields):
    {
        "batch_name": "APR-2026-OFFSHORE",
        "date_closed": "2026-03-31T00:00:00",
        "duration_days": 30,
        "is_active": true
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
        return BatchController.update_batch(batch_id, data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/investor-deployment-dates', methods=['PUT'])
@jwt_required()
@super_admin_required
def update_investor_deployment_dates(batch_id):
    """Super admin: set each client's own deployment date in a deployed batch. Body: {"dates": {"<investment_id>": "YYYY-MM-DD"}}"""
    try:
        data = request.get_json() or {}
        return BatchController.update_investor_deployment_dates(batch_id, data.get("dates"), db.session)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>', methods=['PATCH'])
@jwt_required()
def patch_batch(batch_id):
    """
    Patch (partially update) a batch - for two-stage creation

    Request Body (optional fields):
    {
        "batch_name": "Updated Name",
        "certificate_number": "CERT-001",
        "date_deployed": "2026-03-15T00:00:00",
        "is_active": true
    }

    Advancing stages (transfer / deploy / activate) is normal workflow open to
    any logged-in user, but editing the batch's name or certificate number is
    an edit and is super_admin-only.
    """
    if any(k in (request.get_json(silent=True) or {}) for k in BATCH_EDIT_FIELDS):
        from app.Funds.edit_service import require_role
        _, error_response = require_role(roles=("super_admin",))
        if error_response:
            return error_response
    try:
        data = request.get_json(silent=True)
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)
        
        session = db.session
        return BatchController.patch_batch(batch_id, data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/email-logs', methods=['GET'])
@jwt_required()
def get_batch_email_logs(batch_id):
    """
    Get email delivery logs for a batch and aggregated delivery summary.
    """
    try:
        # Validate batch exists
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        logs_query = db.session.query(EmailLog).filter(EmailLog.batch_id == batch_id).order_by(EmailLog.timestamp.desc())
        logs = logs_query.all()

        log_items = []
        for log in logs:
            item = {
                "id": log.id,
                "investor_id": log.investor_id,
                "investor_email": log.investor.investor_email if log.investor else None,
                "investor_name": log.investor.investor_name if log.investor else None,
                "status": log.status,
                "email_type": log.email_type,
                "recipient_count": log.recipient_count,
                "success_count": log.success_count,
                "failure_count": log.failure_count,
                "error_message": log.error_message,
                "timestamp": log.timestamp.isoformat(),
                "retry_count": log.retry_count,
            }
            log_items.append(item)

        sent = sum(1 for l in logs if l.status.lower() == 'sent')
        failed = sum(1 for l in logs if l.status.lower() == 'failed')
        distinct_investors = len({l.investor_id for l in logs if l.investor_id})

        return make_response(jsonify({
            "status": 200,
            "message": "Email logs retrieved",
            "batch_id": batch_id,
            "summary": {
                "total_attempted": len(logs),
                "sent": sent,
                "failed": failed,
                "distinct_investors": distinct_investors
            },
            "data": log_items
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/history', methods=['GET'])
@jwt_required()
def get_batch_history(batch_id):
    """
    Get batch performance history across all epochs (for charts).
    Returns aggregated batch data per epoch in chronological order.
    
    CRITICAL: Only includes data up to the latest committed ValuationRun.
    This prevents unprocessed months (like October in 'Principal Only' state) from showing in charts.
    """
    try:
        # IMPORTANT: This endpoint must be batch-atomic.
        # EpochLedger is keyed by (internal_client_code, fund_name) and will bleed across batches
        # when the same client code appears in multiple batches. Use BatchValuation instead.
        from app.Valuation.model import BatchValuation, ValuationRun
        from app.Batch.model import Batch
        from sqlalchemy import func
        from decimal import Decimal

        max_chart_epoch = (
            db.session.query(func.max(ValuationRun.epoch_end))
            .filter(func.lower(ValuationRun.status) == "committed")
            .scalar()
        )

        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        q = db.session.query(BatchValuation).filter(BatchValuation.batch_id == batch_id)
        if max_chart_epoch:
            q = q.filter(BatchValuation.period_end_date <= max_chart_epoch)
        valuations = q.order_by(BatchValuation.period_end_date.asc()).all()

        if not valuations:
            return make_response(
                jsonify({"status": 200, "message": "No valuations for batch", "data": []}), 200
            )

        history = []
        prev_end = None
        for v in valuations:
            epoch_end = v.period_end_date
            epoch_start = prev_end
            start_balance = (
                Decimal(str(prev_end.balance_at_end_of_period))
                if prev_end is not None
                else Decimal(str(v.total_principal or 0))
            )
            end_balance = Decimal(str(v.balance_at_end_of_period or 0))

            history.append(
                {
                    "epoch_start": epoch_start.isoformat() if epoch_start else None,
                    "epoch_end": epoch_end.isoformat() if epoch_end else None,
                    "month_name": epoch_end.strftime("%b %d") if epoch_end else "N/A",
                    "performance_pct": round(float(Decimal(str(v.performance_rate or 0)) * 100), 2),
                    "start_balance": round(float(start_balance), 2),
                    "deposits": 0.0,
                    "withdrawals": round(float(Decimal(str(v.total_withdrawals or 0))), 2),
                    "profit": round(float(Decimal(str(v.total_profit or 0))), 2),
                    "end_balance": round(float(end_balance), 2),
                }
            )
            prev_end = v

        return make_response(
            jsonify({"status": 200, "message": "Batch history retrieved", "data": history}), 200
        )

    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/notifications/recent', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True, methods=['GET', 'OPTIONS'])
def get_recent_notifications():
    """Get the 20 most recent notification events (emails sent and batch summaries)."""
    # Handle CORS preflight (OPTIONS request)
    if request.method == 'OPTIONS':
        return make_response('', 204)
    
    # JWT required only for actual GET requests
    from flask_jwt_extended import verify_jwt_in_request
    verify_jwt_in_request()
    
    try:
        # Get recent email events: both individual sends and batch summaries
        rows = db.session.query(EmailLog).filter(
            EmailLog.status.in_(['Sent', 'Summary', 'Failed'])
        ).order_by(EmailLog.timestamp.desc()).limit(20).all()
        
        items = []
        for r in rows:
            batch = db.session.query(Batch).filter(Batch.id == r.batch_id).first() if r.batch_id else None
            
            # Format the event type for display
            if r.email_type == 'BATCH_UPLOAD' and r.status == 'Summary':
                event_type = "Batch Upload"
                description = f"Excel processed with {r.recipient_count} investors"
            elif r.status == 'Summary':
                event_type = f"{r.email_type} Summary"
                description = f"{r.recipient_count} recipients sent"
            elif r.status == 'Sent':
                event_type = f"{r.email_type}"
                description = f"Email sent to {r.recipient_count} recipient(s)"
            elif r.status == 'Failed':
                event_type = f"{r.email_type} (Failed)"
                description = f"Failed to send to {r.failure_count} recipient(s)"
            else:
                event_type = r.email_type
                description = f"{r.status}"
            
            items.append({
                "id": r.id,
                "batch_id": r.batch_id,
                "batch_name": batch.batch_name if batch else None,
                "email_type": r.email_type,
                "event_type": event_type,
                "description": description,
                "recipient_count": r.recipient_count,
                "success_count": r.success_count,
                "failure_count": r.failure_count,
                "timestamp": r.timestamp.isoformat(),
                "status": 'Success' if (r.failure_count or 0) == 0 else 'Failed' if r.status == 'Failed' else 'Partial Failure' if (r.failure_count or 0) > 0 else 'Sent',
            })

        return make_response(jsonify({"status": 200, "message": "Recent notifications retrieved", "data": items}), 200)
    except Exception as e:
        print(f"❌ Error fetching notifications: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}", "data": []}), 500)

        return make_response(jsonify({"status": 200, "message": "Recent notifications retrieved", "data": items}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/notifications/recent/<int:notification_id>/failures', methods=['GET'])
@jwt_required()
def get_notification_failures(notification_id):
    """Get investors/emails which failed for a specific summary notification entry."""
    try:
        summary = db.session.query(EmailLog).filter(EmailLog.id == notification_id, EmailLog.status == 'Summary').first()
        if not summary:
            return make_response(jsonify({"status": 404, "message": "Notification not found"}), 404)

        failures = db.session.query(EmailLog).filter(
            EmailLog.batch_id == summary.batch_id,
            EmailLog.email_type == summary.email_type,
            EmailLog.status == 'Failed'
        ).order_by(EmailLog.timestamp.desc()).all()

        rows = []
        for f in failures:
            inv = db.session.query(Investment).get(f.investor_id) if f.investor_id else None
            rows.append({
                "investor_name": inv.investor_name if inv else None,
                "investor_email": inv.investor_email if inv else None,
                "error_message": f.error_message,
            })

        return make_response(jsonify({"status": 200, "message": "Failure details retrieved", "data": rows}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/toggle-active', methods=['PATCH'])
@jwt_required()
def toggle_active(batch_id):
    """Toggle the is_active status of a batch"""
    try:
        session = db.session
        return BatchController.toggle_active(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/toggle-transferred', methods=['PATCH'])
@jwt_required()
@super_admin_required
def toggle_transferred(batch_id):
    """Toggle the is_transferred status of a batch"""
    try:
        session = db.session
        return BatchController.toggle_transferred(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/update_status', methods=['PATCH'])
@jwt_required()
@super_admin_required
def update_batch_status(batch_id):
    """
    Update batch status and trigger automated emails for multi-stage investment lifecycle
    
    Handles automated email triggers for:
    - Stage 2: Mark as Transferred (is_transferred: true) -> "Funds Transferred" email
    - Stage 3: Date Deployed saved (date_deployed) -> "Investment Active" email  
    - Stage 4: Set Active (is_active: true) -> "Portfolio Live" email
    
    Request Body Examples:
    {
        "is_transferred": true
    }
    {
        "date_deployed": "2026-03-15T00:00:00"
    }
    {
        "is_active": true
    }
    
    Response includes email delivery counts for monitoring.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)
        
        session = db.session
        return BatchController.update_status(batch_id, data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>', methods=['DELETE'])
@jwt_required()
@super_admin_required
def delete_batch(batch_id):
    """Delete a batch and its related investments."""
    try:
        session = db.session
        return BatchController.delete_batch(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error deleting batch: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/update', methods=['PATCH'])
@jwt_required()
@super_admin_required
def update_batch_status_v2(batch_id):
    """
    Compatible update endpoint for checkbox-driven status update.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)

        session = db.session
        return BatchController.update_status(batch_id, data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/notify-transfer', methods=['PATCH'])
@jwt_required()
@super_admin_required
def notify_transfer(batch_id):
    """Explicit endpoint for transfer notification (stage 2)."""
    try:
        session = db.session
        return BatchController.notify_transfer(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


# ==================== NAV-BASED BATCH OPERATIONS ====================

@batch_v1.route('/api/v1/batches/<int:batch_id>/close', methods=['POST'])
@jwt_required()
def close_batch(batch_id):
    """
    Close batch and generate export Excel.
    Response: { "status": 200, "data": { "batch_id": 7, "is_open": false, "exported_at": "...", "export_url": "/api/v1/batches/7/export", "investors_count": 5, "total_deposited": 5000000 } }
    """
    try:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        if not batch.is_open:
            return make_response(jsonify({"status": 400, "message": "Batch is already closed"}), 400)

        # Close batch
        batch.is_open = False
        batch.exported_at = datetime.utcnow()

        # Count investors and total deposited
        investors = db.session.query(Investment).filter(Investment.batch_id == batch_id).all()
        investors_count = len(investors)
        total_deposited = sum(float(inv.amount_deposited) for inv in investors)

        db.session.commit()

        return make_response(jsonify({
            "status": 200,
            "data": {
                "batch_id": batch_id,
                "is_open": False,
                "exported_at": batch.exported_at.isoformat(),
                "export_url": f"/api/v1/batches/{batch_id}/export",
                "investors_count": investors_count,
                "total_deposited": total_deposited
            }
        }), 200)

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/deploy', methods=['PATCH'])
@jwt_required()
@super_admin_required
def deploy_batch_nav(batch_id):
    """
    Deploy batch. Calculate shares for every investor.
    Request: {
      "deployment_date": "2026-04-01",
      "nav_per_share": 1329.4779,
      "total_nav": 1072636.69,
      "total_shares": 771.92,
      "transfer_cost": 150.00,
      "entry_fee_percent": 2.0
    }
    """
    try:
        data = request.get_json()
        required = ['deployment_date', 'nav_per_share', 'total_nav', 'total_shares', 'transfer_cost', 'entry_fee_percent']
        if not all(k in data for k in required):
            return make_response(jsonify({"status": 400, "message": f"Required fields: {', '.join(required)}"}), 400)

        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        if batch.is_open:
            return make_response(jsonify({"status": 400, "message": "Batch must be closed before deployment"}), 400)

        # Get all investments in batch
        investments = db.session.query(Investment).filter(Investment.batch_id == batch_id).all()
        if not investments:
            return make_response(jsonify({"status": 400, "message": "No investments in batch"}), 400)

        nav_per_share = Decimal(str(data['nav_per_share']))
        total_nav = Decimal(str(data['total_nav']))
        total_shares = Decimal(str(data['total_shares']))
        transfer_cost = Decimal(str(data['transfer_cost']))
        entry_fee_percent = Decimal(str(data['entry_fee_percent']))
        deployment_dt = datetime.fromisoformat(data['deployment_date'])
        deployment_date = deployment_dt.date()

        total_principal = sum((inv.amount_deposited or Decimal('0.00')) for inv in investments)
        if total_principal <= Decimal('0.00'):
            return make_response(jsonify({"status": 400, "message": "Total deposit amount must be greater than zero"}), 400)

        investor_data = []
        calculated_total_shares = Decimal('0')
        calculated_total_nav = Decimal('0')
        allocated_transfer = Decimal('0')
        cent = Decimal('0.01')

        for idx, inv in enumerate(investments):
            principal = Decimal(str(inv.amount_deposited))
            if idx == len(investments) - 1:
                transfer_cost_share = (transfer_cost - allocated_transfer).quantize(cent)
            else:
                transfer_cost_share = (principal / total_principal * transfer_cost).quantize(cent)
                allocated_transfer += transfer_cost_share

            net_after_transfer = principal - transfer_cost_share
            # Entry fee is always charged on the initial deposit, not the post-transfer amount.
            entry_fee = (principal * entry_fee_percent / Decimal('100')).quantize(cent)
            net_amount = (net_after_transfer - entry_fee).quantize(cent)
            if net_amount < Decimal('0.00'):
                net_amount = Decimal('0.00')

            shares = (net_amount / nav_per_share).quantize(Decimal('0.0001'))
            market_value = (shares * nav_per_share).quantize(cent)

            # Update investment with share and fee data
            inv.shares_owned = shares
            inv.share_class_id = batch.share_class_id
            inv.deposit_date = deployment_date
            inv.opening_market_value = market_value
            inv.previous_nav_price = nav_per_share
            inv.transfer_fee_deducted = transfer_cost_share
            inv.deployment_fee_deducted = entry_fee
            inv.date_transferred = deployment_dt

            investor_data.append({
                "client_code": inv.internal_client_code,
                "deposit": float(inv.amount_deposited),
                "net_invested": float(net_amount),
                "transaction_fee_usd": float(transfer_cost_share),
                "entry_fee_usd": float(entry_fee),
                "shares": float(shares),
                "deployment_nav": float(nav_per_share),
                "opening_market_value": float(market_value)
            })

            calculated_total_shares += shares
            calculated_total_nav += market_value

        # Validation
        shares_diff = abs(calculated_total_shares - total_shares)
        nav_diff = abs(calculated_total_nav - total_nav)

        if shares_diff > Decimal('0.01') or nav_diff > Decimal('1.00'):
            return make_response(jsonify({
                "status": 400,
                "message": f"Reconciliation failed. Shares diff: {float(shares_diff)}, NAV diff: {float(nav_diff)}"
            }), 400)

        # Update batch
        batch.date_deployed = deployment_dt
        batch.deployment_nav = nav_per_share
        batch.total_shares = calculated_total_shares
        batch.deployment_total_nav = total_nav
        batch.deployment_date_actual = deployment_date
        batch.deployment_confirmed = True
        batch.is_active = True
        batch.is_transferred = True
        batch.transfer_transaction_cost = transfer_cost
        batch.transaction_cost = sum((inv.deployment_fee_deducted or Decimal('0.00')) for inv in investments)

        # Create investor_shares records
        from app.Funds.investor_shares import InvestorShares
        for inv in investments:
            investor_share = InvestorShares(
                investment_id=inv.id,
                share_class_id=batch.share_class_id,
                batch_id=batch_id,
                shares_owned=inv.shares_owned,
                deployment_nav=nav_per_share,
                deployment_date=batch.deployment_date_actual,
                is_active=True
            )
            db.session.add(investor_share)

        db.session.commit()
        BatchController.refresh_cached_total_capital(batch, db.session)
        BatchController._on_batch_deployed(batch, db.session)

        return make_response(jsonify({
            "status": 200,
            "data": {
                "batch_id": batch_id,
                "deployment_date": data['deployment_date'],
                "nav_per_share": float(nav_per_share),
                "total_shares": float(calculated_total_shares),
                "total_nav": float(calculated_total_nav),
                "investors": investor_data,
                "reconciliation": {
                    "calculated_total_shares": float(calculated_total_shares),
                    "diff": float(shares_diff),
                    "status": "PASS"
                }
            }
        }), 200)

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/export', methods=['GET'])
@jwt_required()
def export_batch(batch_id):
    """
    Download closed batch export as CSV.
    """
    try:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        if batch.is_open:
            return make_response(jsonify({"status": 400, "message": "Batch must be closed before export"}), 400)

        investments = db.session.query(Investment).filter(Investment.batch_id == batch_id).order_by(Investment.id.asc()).all()

        output = BytesIO()
        writer = csv.writer(output)

        writer.writerow(["Investment ID", "Investor Name", "Internal Client Code", "Investor Email", "Investor Phone", "Fund ID", "Fund Name", "Amount Deposited", "Date Deposited", "Share Class ID", "Shares Owned", "Deployment NAV"])

        for inv in investments:
            writer.writerow([
                inv.id,
                inv.investor_name,
                inv.internal_client_code,
                inv.investor_email,
                inv.investor_phone,
                inv.fund_id,
                inv.fund_name,
                float(inv.amount_deposited) if inv.amount_deposited is not None else None,
                inv.date_deposited.isoformat() if inv.date_deposited else None,
                getattr(inv, 'share_class_id', None),
                float(getattr(inv, 'shares_owned', None)) if getattr(inv, 'shares_owned', None) is not None else None,
                float(getattr(inv, 'deployment_nav', None)) if getattr(inv, 'deployment_nav', None) is not None else None,
            ])

        output.seek(0)
        filename = f"batch-{batch_id}-export.csv"
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error generating export: {str(e)}"}), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>/investments/export', methods=['GET'])
@jwt_required()
def export_batch_investments(batch_id):
    """
    Task 6: "Export to Excel" for a batch's client list — ALL investments in
    this batch matching the current `search` filter (not just the visible
    page), with the product-relevant columns the batch detail page shows
    (SHARES: net USD, net NGN, allocated shares, refund USD; FUNDS: shares,
    NAV, value). Chunked LIMIT/OFFSET reads + a write-only (streaming)
    worksheet keep this responsive regardless of batch size — unlike
    export_batch's CSV above, this isn't gated on the batch being closed,
    since the batch detail page's client list is viewable at any stage.
    """
    import openpyxl
    from app.utils.audit_log import create_audit_log

    CHUNK_SIZE = 1000
    try:
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        search = (request.args.get("search") or "").strip()
        is_shares = batch.product_type == SHARES

        base_query = db.session.query(Investment).filter(Investment.batch_id == batch_id)
        if search:
            like = f"%{search}%"
            base_query = base_query.filter(
                or_(
                    Investment.internal_client_code.ilike(like),
                    Investment.investor_email.ilike(like),
                    Investment.investor_phone.ilike(like),
                )
            )
        total = base_query.count()

        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(f"{'Shares' if is_shares else 'Funds'} Clients")
        if is_shares:
            headers = [
                "Investor Name", "Client Code", "Deposit (USD)", "Net (USD)", "Net (NGN)",
                "Shares Allocated", "Refund (USD)",
            ]
        else:
            headers = [
                "Investor Name", "Client Code", "Deposit (USD)", "Shares", "NAV / Share", "Value (Market)",
            ]
        ws.append(headers)

        row_count = 0
        for offset in range(0, total, CHUNK_SIZE):
            chunk = base_query.order_by(Investment.id.asc()).offset(offset).limit(CHUNK_SIZE).all()
            if is_shares:
                for inv in chunk:
                    net_usd = float(
                        (inv.amount_deposited or 0) - (inv.deployment_fee_deducted or 0) - (inv.transfer_fee_deducted or 0)
                    )
                    ws.append([
                        inv.investor_name, inv.internal_client_code, float(inv.amount_deposited or 0),
                        net_usd, float(inv.net_ngn) if inv.net_ngn is not None else None,
                        float(inv.shares_owned) if inv.shares_owned is not None else None,
                        float(inv.oversubscription_refund_amount) if inv.oversubscription_refund_amount else None,
                    ])
                    row_count += 1
            else:
                prefetch = BatchController._prefetch_valuation_cascade(db.session, chunk)
                for inv in chunk:
                    try:
                        values = BatchController._calculate_batch_investment_values(inv, batch, db.session, **prefetch)
                        market_value = values["current_balance"]
                    except Exception:
                        market_value = float(inv.net_principal or 0)
                    ws.append([
                        inv.investor_name, inv.internal_client_code, float(inv.amount_deposited or 0),
                        float(inv.shares_owned) if inv.shares_owned is not None else None,
                        float(inv.previous_nav_price) if inv.previous_nav_price is not None else None,
                        market_value,
                    ])
                    row_count += 1

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        create_audit_log(
            action="EXCEL_EXPORT",
            target_type="batch",
            target_id=batch_id,
            target_name=batch.batch_name,
            description=f"Exported batch client list to Excel (batch: {batch.batch_name}, search: {search or '—'})",
            new_value={"scope": f"batch:{batch_id}", "search": search or None, "row_count": row_count},
        )

        filename = f"Batch_{batch_id}_Clients_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error generating export: {str(e)}"}), 500)
