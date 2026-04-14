from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from flask_cors import cross_origin
from app.database.database import db
from app.Batch.controllers import BatchController
from app.Batch.model import Batch
from app.utils.audit_log import audit_log_file_upload
from app.Investments.model import EmailLog, Investment
from datetime import datetime

batch_v1 = Blueprint("batch_v1", __name__, url_prefix='/')

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
    """Get all batches"""
    try:
        session = db.session
        return BatchController.get_all_batches(session)
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
        return BatchController.get_batch_by_id(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@batch_v1.route('/api/v1/batches/<int:batch_id>', methods=['PUT'])
@jwt_required()
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
    """
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


@batch_v1.route('/api/v1/batches/<int:batch_id>/summary', methods=['GET'])
@jwt_required()
def get_batch_summary(batch_id):
    """
    Get complete batch summary including:
    - Batch details (name, dates, status)
    - All investments
    - Performance data (if available)
    - Pro-rata distributions (if calculated)
    """
    try:
        session = db.session
        return BatchController.get_batch_summary(batch_id, session)
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
        from app.Investments.model import Investment, EpochLedger
        from app.Valuation.model import ValuationRun
        from app.Batch.model import Batch
        from sqlalchemy import func, and_
        from decimal import Decimal
        
        print(f"[get_batch_history] Called for batch_id={batch_id}")
        
        # ── CRITICAL: Find the LAST PROCESSED epoch (Sept 2026) ──
        max_chart_epoch = db.session.query(
            func.max(ValuationRun.epoch_end)
        ).filter(
            func.lower(ValuationRun.status) == "committed"
        ).scalar()
        print(f"[get_batch_history] max_chart_epoch: {max_chart_epoch}")
        
        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            print(f"[get_batch_history] Batch {batch_id} not found")
            return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

        # Get all investments for this batch
        investments = db.session.query(Investment).filter(Investment.batch_id == batch_id).all()
        print(f"[get_batch_history] Found {len(investments)} investments")
        if not investments:
            print(f"[get_batch_history] No investments found")
            return make_response(jsonify({"status": 200, "message": "No investments in batch", "data": []}), 200)

        investor_codes = [inv.internal_client_code for inv in investments]
        print(f"[get_batch_history] Investor codes: {investor_codes}")
        
        # Get all distinct epochs that have data for this batch
        epoch_query = (
            db.session.query(
                EpochLedger.epoch_start,
                EpochLedger.epoch_end,
            )
            .filter(EpochLedger.internal_client_code.in_(investor_codes))
        )
        
        # Restrict to max_chart_epoch (exclude unprocessed months)
        if max_chart_epoch:
            epoch_query = epoch_query.filter(EpochLedger.epoch_end <= max_chart_epoch)
        
        epochs = (
            epoch_query
            .distinct()
            .order_by(EpochLedger.epoch_start.asc(), EpochLedger.epoch_end.asc())
            .all()
        )
        print(f"[get_batch_history] Found {len(epochs)} distinct epochs")

        history = []
        for epoch_start, epoch_end in epochs:
            # Aggregate all ledger entries for this batch at this epoch
            ledger_rows = (
                db.session.query(EpochLedger)
                .filter(
                    and_(
                        EpochLedger.internal_client_code.in_(investor_codes),
                        EpochLedger.epoch_start == epoch_start,
                        EpochLedger.epoch_end == epoch_end,
                    )
                )
                .all()
            )

            if ledger_rows:
                total_start = sum(Decimal(str(e.start_balance or 0)) for e in ledger_rows)
                total_deposits = sum(Decimal(str(e.deposits or 0)) for e in ledger_rows)
                total_withdrawals = sum(Decimal(str(e.withdrawals or 0)) for e in ledger_rows)
                total_profit = sum(Decimal(str(e.profit or 0)) for e in ledger_rows)
                total_end = sum(Decimal(str(e.end_balance or 0)) for e in ledger_rows)

                # Get performance rate from ValuationRun if available
                vr_rows = (
                    db.session.query(ValuationRun)
                    .filter(
                        and_(
                            ValuationRun.epoch_start == epoch_start,
                            ValuationRun.epoch_end == epoch_end,
                        )
                    )
                    .order_by(ValuationRun.id.desc())
                    .limit(1)
                    .all()
                )
                
                performance_pct = 0.0
                if vr_rows and vr_rows[0].performance_rate:
                    performance_pct = float(vr_rows[0].performance_rate) * 100

                # Format chart label as month + day to avoid ambiguity (e.g. Apr 26)
                month_name = epoch_end.strftime('%b %d') if epoch_end else "N/A"

                history.append({
                    "epoch_start": epoch_start.isoformat() if epoch_start else None,
                    "epoch_end": epoch_end.isoformat() if epoch_end else None,
                    "month_name": month_name,
                    "performance_pct": round(float(performance_pct), 2),
                    "start_balance": round(float(total_start), 2),
                    "deposits": round(float(total_deposits), 2),
                    "withdrawals": round(float(total_withdrawals), 2),
                    "profit": round(float(total_profit), 2),
                    "end_balance": round(float(total_end), 2),
                })

        print(f"[get_batch_history] Returning {len(history)} history entries")
        return make_response(jsonify({
            "status": 200,
            "message": "Batch history retrieved",
            "data": history
        }), 200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[get_batch_history] Error: {str(e)}")
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


@batch_v1.route('/api/v1/batches/<int:batch_id>/upload-excel', methods=['POST'])
@jwt_required()
def upload_batch_excel(batch_id):
    """
    Upload Excel file with investor data for a specific batch
    
    Expected Excel columns:
    - Client Name -> investor_name
    - Internal client code -> internal_client_code
    - Amount(usd) -> amount_deposited
    - funds -> fund_name
    
    Returns:
    {
        "status": 201,
        "message": "...",
        "data": {
            "batch_id": ...,
            "imported_investments": ...,
            "total_amount": ...
        }
    }
    """
    try:
        if 'file' not in request.files:
            return make_response(jsonify({
                "status": 400,
                "message": "No file part in the request"
            }), 400)
        
        file = request.files['file']
        if file.filename == '':
            return make_response(jsonify({
                "status": 400,
                "message": "No selected file"
            }), 400)
        
        session = db.session
        response = BatchController.upload_batch_excel(batch_id, file, session)
        
        # Extract status and data from response object
        response_data = response.get_json()
        status_code = response.status_code
        
        # Log the file upload with row count from imported_investments
        if status_code == 201 and response_data.get('data'):
            row_count = response_data['data'].get('imported_investments', 0)
            audit_log_file_upload(
                filename=file.filename,
                batch_id=batch_id,
                row_count=row_count,
                status=True
            )
        
        return response
    except Exception as e:
        # Log failed upload
        audit_log_file_upload(
            filename=request.files['file'].filename if 'file' in request.files else 'Unknown',
            batch_id=batch_id,
            row_count=0,
            status=False,
            error=str(e)
        )
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)
