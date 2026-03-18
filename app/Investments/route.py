from flask import request, Blueprint, jsonify, make_response, send_file
from flask_jwt_extended import jwt_required
from app.database.database import db
from app.Investments.controllers import InvestmentController
from app.Investments.model import Investment
from app.Investments.model import EpochLedger, Withdrawal
from app.Batch.core_fund import CoreFund
from app.Valuation.model import ValuationRun
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from sqlalchemy import func
from decimal import Decimal
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

investment_v1 = Blueprint("investment_v1", __name__, url_prefix='/api/v1')

# ==================== INVESTMENT ENDPOINTS ====================

@investment_v1.route('/investments', methods=['POST'])
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
        data = request.get_json()
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


@investment_v1.route('/investments/<int:investment_id>', methods=['GET'])
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


@investment_v1.route('/batches/<int:batch_id>/investments', methods=['GET'])
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


@investment_v1.route('/batches/<int:batch_id>/investments', methods=['POST'])
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


@investment_v1.route('/investments/<int:investment_id>', methods=['PUT'])
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


@investment_v1.route('/investments/<int:investment_id>', methods=['DELETE'])
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


@investment_v1.route('/investments/upload', methods=['POST'])
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


@investment_v1.route('/investors/<string:client_code>/statement', methods=['GET'])
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
            return make_response(jsonify({
                "status": 200,
                "message": "Statement retrieved",
                "count": 0,
                "data": {
                    "client_code": client_code,
                    "investor_name": None,
                    "funds": [],
                    "summary": {"opening_balance": 0.0, "net_growth": 0.0, "closing_balance": 0.0},
                    "periods": [],
                    "history": [],
                    "latest_audit_hash": None,
                }
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


@investment_v1.route('/investors/<string:client_code>/statement/pdf', methods=['GET'])
@jwt_required()
def download_investor_statement_pdf(client_code):
    """
    Generate a branded investor statement PDF from EpochLedger periods.
    """
    try:
        # Reuse the JSON payload builder
        json_res = get_investor_statement(client_code)
        payload = json_res.get_json() if hasattr(json_res, "get_json") else None
        if not payload or payload.get("status") != 200:
            return json_res

        data = payload.get("data") or {}
        periods = data.get("periods") or []
        history = data.get("history") or []

        # Create PDF
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
            fontSize=12,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )
        small_style = ParagraphStyle(
            'Small',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#333333'),
        )

        investor_name = data.get("investor_name") or "Investor"
        code = data.get("client_code") or client_code
        funds = ", ".join(data.get("funds") or [])
        summary = data.get("summary") or {}
        latest_hash = data.get("latest_audit_hash") or ""

        story.append(Paragraph("AIB-AXYS Africa", title_style))
        story.append(Paragraph("Investor Statement (Epoch Ledger)", heading_style))
        story.append(Spacer(1, 0.12 * inch))

        info_data = [
            ["Investor Name:", investor_name],
            ["Internal Client Code:", code],
            ["Fund(s):", funds or "—"],
            ["Generated:", datetime.utcnow().strftime('%B %d, %Y')],
        ]
        info_table = Table(info_data, colWidths=[1.7 * inch, 4.8 * inch])
        info_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#00005b')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.15 * inch))

        # Summary box
        summary_data = [
            ["Opening Balance", f"${float(summary.get('opening_balance') or 0):,.2f}"],
            ["Net Growth", f"${float(summary.get('net_growth') or 0):,.2f}"],
            ["Closing Balance", f"${float(summary.get('closing_balance') or 0):,.2f}"],
        ]
        summary_table = Table(summary_data, colWidths=[2.5 * inch, 2.0 * inch])
        summary_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#00005b')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f7fa')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(Paragraph("Summary", heading_style))
        story.append(summary_table)
        story.append(Spacer(1, 0.15 * inch))

        # History table (flattened)
        story.append(Paragraph("History", heading_style))
        history_rows = [["Date", "Description", "Amount", "Running Balance"]]
        for h in history:
            history_rows.append([
                (h.get("date") or "")[:10],
                (h.get("description") or "")[:50],
                f"${float(h.get('amount') or 0):,.2f}",
                f"${float(h.get('running_balance') or 0):,.2f}",
            ])
        if len(history_rows) == 1:
            history_rows.append(["—", "No activity", "$0.00", f"${float(summary.get('closing_balance') or 0):,.2f}"])

        hist_table = Table(history_rows, colWidths=[0.9 * inch, 3.4 * inch, 1.1 * inch, 1.3 * inch])
        hist_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00005b')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(hist_table)
        story.append(Spacer(1, 0.2 * inch))

        # Footer hash (latest valuation hash)
        if latest_hash:
            story.append(Paragraph(f"Audit Hash (latest): <font name='Helvetica-Bold'>{latest_hash}</font>", small_style))
        else:
            story.append(Paragraph("Audit Hash (latest): —", small_style))

        doc.build(story)
        pdf_buffer.seek(0)

        filename = f"Statement_{code}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
        return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ==================== INVESTOR REGISTRY (GLOBAL) ====================

@investment_v1.route('/investors', methods=['GET'])
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


@investment_v1.route('/investors/<string:client_code>', methods=['GET'])
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

        return make_response(jsonify({
            "status": 200,
            "message": "Investor profile retrieved",
            "data": {
                "client_code": client_code,
                "investor_name": investments[-1].investor_name,
                "investor_email": investments[-1].investor_email,
                "investor_phone": investments[-1].investor_phone,
                "total_deposited": float(sum(inv.amount_deposited for inv in investments)),
                "total_profit": float(total_profit),
                "current_value": float(current_value),
                "investments": inv_data,
                "ledger": ledger_data
            }
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/investors/<string:client_code>', methods=['PATCH'])
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

        if not updates:
            return make_response(jsonify({"status": 400, "message": "No updatable fields provided"}), 400)

        q.update(updates, synchronize_session=False)
        session.commit()

        return make_response(jsonify({"status": 200, "message": "Investor updated", "data": {"client_code": client_code, **updates}}), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ==================== WITHDRAWALS ====================

@investment_v1.route('/withdrawals', methods=['POST'])
@jwt_required()
def create_withdrawal():
    """
    Create a withdrawal request.
    Body: { client_id, amount, fund_id, status } where status defaults Pending.
    client_id == internal_client_code
    """
    try:
        data = request.get_json() or {}
        client_id = (data.get('client_id') or '').strip()
        if not client_id:
            return make_response(jsonify({"status": 400, "message": "client_id is required"}), 400)

        fund_id = data.get('fund_id')
        if fund_id is None:
            return make_response(jsonify({"status": 400, "message": "fund_id is required"}), 400)
        fund_id = int(fund_id)

        core = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not core:
            return make_response(jsonify({"status": 404, "message": "Core fund not found"}), 404)

        amount = data.get('amount')
        if amount is None:
            return make_response(jsonify({"status": 400, "message": "amount is required"}), 400)

        status = (data.get('status') or 'Pending').strip().capitalize()
        if status not in ('Pending', 'Approved', 'Rejected'):
            return make_response(jsonify({"status": 400, "message": "status must be Pending|Approved|Rejected"}), 400)

        w = Withdrawal(
            internal_client_code=client_id,
            fund_id=fund_id,
            fund_name=core.fund_name,
            amount=amount,
            status=status,
            approved_at=datetime.utcnow() if status == 'Approved' else None,
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


@investment_v1.route('/withdrawals', methods=['GET'])
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
            q = q.filter(Withdrawal.status == status.capitalize())
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
        return make_response(jsonify({"status": 200, "message": "Withdrawals retrieved", "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/withdrawals/<int:withdrawal_id>', methods=['PATCH'])
@jwt_required()
def update_withdrawal(withdrawal_id: int):
    """
    Approve/Reject a withdrawal.
    Body: { status: 'Approved'|'Rejected' }
    """
    try:
        data = request.get_json() or {}
        status = (data.get('status') or '').strip().capitalize()
        if status not in ('Approved', 'Rejected'):
            return make_response(jsonify({"status": 400, "message": "status must be Approved or Rejected"}), 400)

        w = db.session.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
        if not w:
            return make_response(jsonify({"status": 404, "message": "Withdrawal not found"}), 404)

        w.status = status
        w.approved_at = datetime.utcnow() if status == 'Approved' else None
        db.session.commit()
        return make_response(jsonify({"status": 200, "message": "Withdrawal updated"}), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)
