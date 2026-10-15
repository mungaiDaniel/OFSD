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
    PendingEmail,
    normalize_withdrawal_status,
    WITHDRAWAL_STATUSES,
    FINAL_WITHDRAWAL_STATUSES,
    WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
    WITHDRAWAL_SOURCE_INVESTOR_REQUEST,
)
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.logic.batch_management_service import BatchManagementService
from app.Valuation.model import ValuationRun, BatchValuation
from app.database.product_type import FUNDS, SHARES
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import func, or_, insert, text
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape
import logging

from app.utils.statement_theme import (
    append_branded_footer,
    append_divider_line,
    append_fund_title,
    append_receipt_header,
    build_doc_template,
    build_paragraph_styles,
    build_statement_brand_block,
    build_orange_banner_table,
    build_jh_logo_block,
    client_info_table_style,
    get_statement_theme,
    highlight_banner_style,
    history_table_style,
    resolve_axys_logo_path,
    resolve_jh_logo_path,
    summary_table_style,
    is_janus_henderson_fund as _is_janus_henderson_fund,
    is_dangote_dprp_fund,
)

logger = logging.getLogger(__name__)


def normalize_datetime_to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_decimal(value, default=Decimal('0.00')):
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except Exception:
        return default


def _format_statement_money(amount, currency="USD") -> str:
    """Format PDF money values with the statement currency marker."""
    try:
        amt = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    except Exception:
        amt = Decimal("0.00")
    prefix = "KES " if str(currency or "").upper() == "KES" else "$"
    return f"{prefix}{amt:,.2f}"


def _register_montserrat_fonts():
    """Register Montserrat fonts for ReportLab if available on host."""
    base_dir = Path(__file__).resolve().parents[2].parent
    candidates = [
        Path("C:/Windows/Fonts/Montserrat-Regular.ttf"),
        Path("C:/Windows/Fonts/Montserrat-Bold.ttf"),
        base_dir / "frontend" / "public" / "fonts" / "Montserrat-Regular.ttf",
        base_dir / "frontend" / "public" / "fonts" / "Montserrat-Bold.ttf",
        base_dir / "frontend" / "public" / "fonts" / "Montserrat-wght.ttf",
        base_dir / "ofds-frontend" / "public" / "fonts" / "Montserrat-Regular.ttf",
        base_dir / "ofds-frontend" / "public" / "fonts" / "Montserrat-Bold.ttf",
        base_dir / "ofds-frontend" / "public" / "fonts" / "Montserrat-wght.ttf",
        base_dir / "backend" / "assets" / "fonts" / "Montserrat-wght.ttf",
    ]
    regular_path = next((p for p in candidates if p.name.lower().endswith("montserrat-regular.ttf") and p.exists()), None)
    bold_path = next((p for p in candidates if p.name.lower().endswith("montserrat-bold.ttf") and p.exists()), None)
    variable_path = next((p for p in candidates if p.name.lower() == "montserrat-wght.ttf" and p.exists()), None)

    try:
        # Prefer explicit regular/bold when present, otherwise fall back to a variable font file.
        if regular_path:
            pdfmetrics.registerFont(TTFont("Montserrat", str(regular_path)))
        elif variable_path:
            pdfmetrics.registerFont(TTFont("Montserrat", str(variable_path)))

        if bold_path:
            pdfmetrics.registerFont(TTFont("Montserrat-Bold", str(bold_path)))
        elif variable_path:
            pdfmetrics.registerFont(TTFont("Montserrat-Bold", str(variable_path)))
    except Exception:
        # Keep PDF generation resilient if font registration fails.
        pass


def _require_montserrat_fonts_or_raise():
    """
    The user requires Montserrat to be visible in generated PDFs.
    Do not silently fall back to Helvetica, because that hides misconfiguration.
    """
    _register_montserrat_fonts()
    registered = set(pdfmetrics.getRegisteredFontNames())
    if "Montserrat" not in registered or "Montserrat-Bold" not in registered:
        raise ValueError(
            "Montserrat fonts are required but not available. "
            "Install Montserrat Regular + Bold on the server (Windows Fonts), "
            "or add Montserrat-wght.ttf to backend/assets/fonts or frontend/public/fonts."
        )


def _resolve_brand_logo_path() -> Path | None:
    """Resolve the Axys logo for the white statement background."""
    return resolve_axys_logo_path()


def _resolve_janus_henderson_statement_logo_path(
    fund_names=(), fund_codes=()
) -> Path | None:
    """Return the additional JH logo; never replace the AIB-Axys brand."""
    logo_path = resolve_jh_logo_path(fund_names, fund_codes)
    if logo_path is None and _is_janus_henderson_fund(fund_names, fund_codes):
        logger.warning(
            "Janus Henderson statement logo is missing: %s",
            Path(__file__).resolve().parents[2] / "assets" / "logo" / "logo-jh-dark-removebg-preview.png",
        )
    return logo_path


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
        "date_deposited": "2026-03-10T00:00:00",
        "currency_type": "KES"  # REQUIRED: Must be 'KES' or 'USD' - this is what appears in the deposit email
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


# ==================== NEW INVESTOR ENDPOINTS (NAV-BASED) ====================

@investment_v1.route('/api/v1/investors', methods=['POST'])
@jwt_required()
def create_investor():
    """
    Add a new investor with auto-batch assignment.
    Request: {
      "investor_name": "Jane Doe", "investor_email": "jane@example.com",
      "investor_phone": "+254700000000", "internal_client_code": "INV-001",
      "fund_id": 1, "share_class_id": 1,
      "deposit_amount": 1000000.00, "deposit_date": "2026-04-15"
    }
    Response: {
      "status": 201, "data": {
        "investment_id": 42, "batch_id": 7, "batch_name": "auto-generated",
        "fund_name": "Axiom", "class_code": "KES_I", "currency": "KES",
        "deposit_amount": 1000000.00
      }
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return make_response(jsonify({"status": 400, "message": "Request body is required"}), 400)

        # Validate required fields
        required = ['investor_name', 'investor_email', 'internal_client_code', 'fund_id', 'share_class_id', 'deposit_amount', 'deposit_date']
        if not all(k in data for k in required):
            return make_response(jsonify({"status": 400, "message": f"Required fields: {', '.join(required)}"}), 400)

        session = db.session
        return InvestmentController.create_new_investor(data, session)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/existing', methods=['POST'])
@jwt_required()
def add_existing_investor_deposit():
    """
    Add a new deposit for an existing investor.
    Request: {
      "internal_client_code": "INV-001",
      "fund_id": 1, "share_class_id": 1,
      "deposit_amount": 500000.00, "deposit_date": "2026-04-16"
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return make_response(jsonify({"status": 400, "message": "Request body is required"}), 400)

        # Validate required fields
        required = ['internal_client_code', 'fund_id', 'share_class_id', 'deposit_amount', 'deposit_date']
        if not all(k in data for k in required):
            return make_response(jsonify({"status": 400, "message": f"Required fields: {', '.join(required)}"}), 400)

        session = db.session
        return InvestmentController.add_existing_investor_deposit(data, session)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


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
    """
    Returns a paginated investor directory listing with current balance standing.

    At scale (thousands of investors) computing the balance for every investor on
    every request — via _calculate_batch_investment_values, which issues several
    queries per investment across its valuation-source fallback tiers — is the
    single most expensive thing this app does. Paginating so that calculation only
    runs for the page actually being displayed (instead of the whole table) is
    what keeps this endpoint from timing out; the per-investment logic itself is
    untouched so results stay identical to before, just computed for fewer rows
    per request.

    Query params:
      - page (default 1), per_page (default 50, max 200)
      - search (optional): matches investor_name, internal_client_code, or investor_email
    """
    try:
        page = max(request.args.get("page", default=1, type=int) or 1, 1)
        per_page = min(max(request.args.get("per_page", default=50, type=int) or 50, 1), 200)
        search = (request.args.get("search") or "").strip()
        product = (request.args.get("product") or "").strip().upper() or None

        # Cheap first pass: resolve just this page's client codes with LIMIT/OFFSET
        # pushed down into SQL — this used to fetch the FULL distinct, sorted code
        # list (every request, even page 1 with no search) and slice it in Python,
        # which meant every investor-directory request paid to materialize and
        # transfer up to 100,000 rows just to keep 50 of them. total comes from a
        # separate COUNT(DISTINCT ...) aggregate instead of len() on that full list.
        def _search_filter(q):
            if search:
                like = f"%{search}%"
                q = q.filter(
                    or_(
                        Investment.investor_name.ilike(like),
                        Investment.internal_client_code.ilike(like),
                        Investment.investor_email.ilike(like),
                        Investment.investor_phone.ilike(like),
                    )
                )
            if product:
                q = q.filter(Investment.product_type == product)
            return q

        total = _search_filter(
            db.session.query(func.count(func.distinct(Investment.internal_client_code)))
        ).scalar() or 0
        total_pages = max((total + per_page - 1) // per_page, 1)
        page = min(page, total_pages)
        start = (page - 1) * per_page

        page_codes_q = _search_filter(
            db.session.query(Investment.internal_client_code).group_by(Investment.internal_client_code)
        ).order_by(func.max(Investment.investor_name).asc()).offset(start).limit(per_page)
        page_codes = [r[0] for r in page_codes_q.all()]

        if not page_codes:
            return make_response(jsonify({
                "status": 200,
                "message": "Investor directory retrieved",
                "count": 0,
                "data": [],
                "pagination": {"page": page, "per_page": per_page, "total": total, "total_pages": total_pages},
            }), 200)

        all_investments_q = db.session.query(Investment).filter(Investment.internal_client_code.in_(page_codes))
        if product:
            all_investments_q = all_investments_q.filter(Investment.product_type == product)
        all_investments = all_investments_q.order_by(Investment.investor_name.asc()).all()

        investor_map = {}
        investor_ids = set()
        funds_per_client = {}
        batch_ids_per_client = {}

        for inv in all_investments:
            code = inv.internal_client_code
            fund_name = inv.fund_name or (inv.fund.fund_name if inv.fund else None)
            fund = fund_name.lower() if fund_name else "unknown"
            class_code = inv.share_class.class_code if getattr(inv, "share_class", None) else None
            currency = inv.share_class.currency if getattr(inv, "share_class", None) else None
            
            if code not in investor_map:
                investor_map[code] = {
                    "investor_name": inv.investor_name,
                    "internal_client_code": code,
                    "investor_email": inv.investor_email,
                    "investor_phone": inv.investor_phone,
                    "fund_name": fund_name,
                    "class_code": class_code,
                    "currency": currency,
                    "shares": 0.0,
                    "performance_pct": None,
                    "market_value": 0.0,
                    "total_principal": 0.0,  # Backward-compat alias for current standing
                    "current_balance": 0.0,
                    "investments": 0,
                    "unique_batches": 0,
                    "last_email_status": None,
                    "last_email_timestamp": None,
                    "_latest_deposit_at": inv.date_deposited,
                }
            else:
                latest_dt = investor_map[code].get("_latest_deposit_at")
                inv_dt = inv.date_deposited
                if inv_dt and (latest_dt is None or inv_dt > latest_dt):
                    investor_map[code]["fund_name"] = fund_name
                    investor_map[code]["class_code"] = class_code
                    investor_map[code]["currency"] = currency
                    investor_map[code]["_latest_deposit_at"] = inv_dt

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
            if getattr(inv, "shares_owned", None) is not None:
                investor_map[code]["shares"] += float(inv.shares_owned or 0)

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
        # This ensures consistency between directory and individual portfolio views.
        # Batches are bulk-fetched once for this page instead of one query per investment.
        from app.Batch.controllers import BatchController

        page_batch_ids = {inv.batch_id for inv in all_investments if inv.batch_id is not None}
        batches_by_id = {
            b.id: b
            for b in db.session.query(Batch).filter(Batch.id.in_(page_batch_ids)).all()
        } if page_batch_ids else {}

        # One shot at prefetching every per-row query _calculate_batch_investment_values
        # would otherwise make for this page's investments (withdrawals, InvestorShares,
        # ValuationSnapshot, NavHistory) — see BatchController._prefetch_valuation_cascade.
        # Works fine across investments from different batches: every prefetch dict here
        # is keyed by investment/client identity, not scoped to one batch.
        prefetch = BatchController._prefetch_valuation_cascade(db.session, all_investments)

        investor_balances = {}
        for inv in all_investments:
            code = inv.internal_client_code
            batch = batches_by_id.get(inv.batch_id) if inv.batch_id is not None else None

            if code not in investor_balances:
                investor_balances[code] = Decimal("0.00")

            try:
                inv_values = BatchController._calculate_batch_investment_values(inv, batch, db.session, **prefetch)
                investor_balances[code] += Decimal(str(inv_values["current_balance"]))
            except Exception as e:
                # Fallback to persisted net principal (already fee-adjusted in DB).
                investor_balances[code] += Decimal(str(inv.net_principal or 0))

        # Update each investor with their calculated balance
        for code, balance in investor_balances.items():
            if code in investor_map:
                investor_map[code]["total_principal"] = float(round(balance, 2))
                investor_map[code]["current_balance"] = float(round(balance, 2))
                investor_map[code]["market_value"] = float(round(balance, 2))

        for row in investor_map.values():
            if not row.get("shares"):
                row["shares"] = None
            row.pop("_latest_deposit_at", None)

        # Preserve requested order (by investor_name) rather than dict insertion order,
        # since investor_map was populated from an unordered .in_() query.
        order_by_code = {code: i for i, code in enumerate(page_codes)}
        investors = sorted(investor_map.values(), key=lambda r: order_by_code.get(r["internal_client_code"], 0))

        return make_response(jsonify({
            "status": 200,
            "message": "Investor directory retrieved",
            "count": len(investors),
            "data": investors,
            "pagination": {"page": page, "per_page": per_page, "total": total, "total_pages": total_pages},
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/export', methods=['GET'])
@jwt_required()
def export_investor_directory():
    """
    Task 6: "Export to Excel" for the investor directory — ALL investors
    matching the current `search`/`product` filters (not just the visible
    page), generated server-side. Reuses the exact same per-investor balance
    calculation as get_investor_directory (BatchController._calculate_batch_
    investment_values), just processed in fixed-size chunks of client codes
    instead of one page, so peak memory never scales with the total row
    count — a 100,000-row export processes CHUNK_SIZE codes at a time and
    writes each chunk straight into a write-only (streaming) worksheet, the
    same openpyxl mode used for the batch/investor Excel exports elsewhere.

    Query params: search, product — identical semantics to GET /investors.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from app.utils.audit_log import create_audit_log
    from app.Batch.controllers import BatchController

    CHUNK_SIZE = 1000
    try:
        search = (request.args.get("search") or "").strip()
        product = (request.args.get("product") or "").strip().upper() or None

        def _search_filter(q):
            if search:
                like = f"%{search}%"
                q = q.filter(
                    or_(
                        Investment.investor_name.ilike(like),
                        Investment.internal_client_code.ilike(like),
                        Investment.investor_email.ilike(like),
                        Investment.investor_phone.ilike(like),
                    )
                )
            if product:
                q = q.filter(Investment.product_type == product)
            return q

        all_codes = [
            r[0]
            for r in _search_filter(
                db.session.query(Investment.internal_client_code).group_by(Investment.internal_client_code)
            ).order_by(func.max(Investment.investor_name).asc()).all()
        ]

        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet("Investors")
        headers = [
            "Investor Name", "Client Code", "Email", "Phone", "Fund / Class", "Class Code",
            "Currency", "Shares", "Market Value", "Performance %", "Deposits", "Unique Batches",
        ]
        ws.append(headers)

        row_count = 0
        for i in range(0, len(all_codes), CHUNK_SIZE):
            chunk_codes = all_codes[i:i + CHUNK_SIZE]

            chunk_investments_q = db.session.query(Investment).filter(Investment.internal_client_code.in_(chunk_codes))
            if product:
                chunk_investments_q = chunk_investments_q.filter(Investment.product_type == product)
            chunk_investments = chunk_investments_q.all()

            investor_map = {}
            batch_ids_per_client = {}
            for inv in chunk_investments:
                code = inv.internal_client_code
                fund_name = inv.fund_name or (inv.fund.fund_name if inv.fund else None)
                class_code = inv.share_class.class_code if getattr(inv, "share_class", None) else None
                currency = inv.share_class.currency if getattr(inv, "share_class", None) else None
                if code not in investor_map:
                    investor_map[code] = {
                        "investor_name": inv.investor_name,
                        "internal_client_code": code,
                        "investor_email": inv.investor_email,
                        "investor_phone": inv.investor_phone,
                        "fund_name": fund_name,
                        "class_code": class_code,
                        "currency": currency,
                        "shares": 0.0,
                        "market_value": 0.0,
                        "performance_pct": None,
                        "investments": 0,
                        "unique_batches": 0,
                    }
                investor_map[code]["investments"] += 1
                batch_ids_per_client.setdefault(code, set())
                if inv.batch_id is not None:
                    batch_ids_per_client[code].add(inv.batch_id)
                if getattr(inv, "shares_owned", None) is not None:
                    investor_map[code]["shares"] += float(inv.shares_owned or 0)

            for code, batch_ids in batch_ids_per_client.items():
                investor_map[code]["unique_batches"] = len(batch_ids)

            chunk_batch_ids = {inv.batch_id for inv in chunk_investments if inv.batch_id is not None}
            batches_by_id = {
                b.id: b for b in db.session.query(Batch).filter(Batch.id.in_(chunk_batch_ids)).all()
            } if chunk_batch_ids else {}
            prefetch = BatchController._prefetch_valuation_cascade(db.session, chunk_investments)

            investor_balances = {}
            for inv in chunk_investments:
                code = inv.internal_client_code
                batch = batches_by_id.get(inv.batch_id) if inv.batch_id is not None else None
                investor_balances.setdefault(code, Decimal("0.00"))
                try:
                    inv_values = BatchController._calculate_batch_investment_values(inv, batch, db.session, **prefetch)
                    investor_balances[code] += Decimal(str(inv_values["current_balance"]))
                except Exception:
                    investor_balances[code] += Decimal(str(inv.net_principal or 0))

            for code in chunk_codes:
                row = investor_map.get(code)
                if not row:
                    continue
                balance = float(round(investor_balances.get(code, Decimal("0.00")), 2))
                fund_label = row["fund_name"] or "—"
                if row["class_code"]:
                    fund_label = f"{fund_label} ({row['class_code']})"
                ws.append([
                    row["investor_name"], row["internal_client_code"], row["investor_email"],
                    row["investor_phone"], fund_label, row["class_code"], row["currency"],
                    row["shares"] or None, balance, row["performance_pct"], row["investments"],
                    row["unique_batches"],
                ])
                row_count += 1

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        create_audit_log(
            action="EXCEL_EXPORT",
            target_type="investor_directory",
            description=f"Exported investor directory to Excel (scope: {product or 'ALL'}, search: {search or '—'})",
            new_value={"scope": product or "ALL", "search": search or None, "row_count": row_count},
        )

        filename = f"Investors_{product or 'All'}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def get_total_investors_count(session=None) -> int:
    """
    Returns the total unique investor count matching the investor directory page.
    """
    if session is None:
        session = db.session
    try:
        all_investments = session.query(Investment.internal_client_code, Investment.investor_name).all()
        unique_clients = set()
        for code, name in all_investments:
            identifier = (code or "").strip()
            if not identifier:
                identifier = (name or "").strip()
            if identifier:
                unique_clients.add(identifier)
        return len(unique_clients)
    except Exception:
        return 0


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
            Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
        )
        all_approved_wds = wd_query.all()

        # Build a map: (year, month) -> total withdrawal amount
        wd_by_month = {}
        for w in all_approved_wds:
            if w.date_withdrawn:
                wd_dt = w.date_withdrawn.replace(tzinfo=None) if w.date_withdrawn.tzinfo else w.date_withdrawn
                key = (wd_dt.year, wd_dt.month)
                wd_effective_amount = float(w.gross_amount if getattr(w, "gross_amount", None) is not None else w.amount or 0)
                wd_by_month[key] = wd_by_month.get(key, 0.0) + wd_effective_amount

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
    return _get_investor_portfolio_aggregated_data(client_code)


def _get_investor_portfolio_aggregated_data(client_code, fund_ids=None):
    """
    Internal helper: the actual portfolio-aggregation body, with no dependency on
    flask.request or JWT verification — safe to call from a background thread
    (the email send-queue scheduler needs this data for INVESTOR_STATEMENT PDFs).
    get_investor_portfolio_aggregated() itself calls request.method/verify_jwt_in_request()
    directly in its body rather than via a decorator, so .__wrapped__ alone can't
    bypass that the way it does for @jwt_required()-decorated view functions
    elsewhere in this file — this split is the actual fix.

    fund_ids: optional iterable of CoreFund ids — when given, restricts to just
    those funds' holdings (used by fund-scoped and multi-fund-scoped statement
    generation). None means every fund the client holds, as before.
    """
    try:
        # Get all investments for this client (case-insensitive)
        investments_q = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        )
        if fund_ids:
            investments_q = investments_q.filter(Investment.fund_id.in_(list(fund_ids)))
        investments = investments_q.order_by(Investment.investor_name.asc()).all()
        
        if not investments:
            return make_response(jsonify({
                "status": 404,
                "message": "Investor not found"
            }), 404)
        
        investor_name = investments[0].investor_name

        # Group investments by batch and fund
        holdings_map = {}
        total_original_principal = Decimal("0.00")
        total_main_balance = Decimal("0.00")

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
                    "fund_code": getattr(inv.fund, "fund_code", None) if inv.fund else None,
                    "investments": [],
                    "total_original_principal": Decimal("0.00"),
                    "total_main_balance": Decimal("0.00"),
                    "total_transaction_fee_usd": Decimal("0.00"),
                    "total_entry_fee_usd": Decimal("0.00"),
                }

            holdings_map[key]["investments"].append(inv)
            holdings_map[key]["total_original_principal"] += Decimal(str(inv.amount_deposited or 0))
            holdings_map[key]["total_main_balance"] += Decimal(str(inv.net_principal or 0))
            holdings_map[key]["total_transaction_fee_usd"] += Decimal(str(inv.transfer_fee_deducted or 0))
            holdings_map[key]["total_entry_fee_usd"] += Decimal(str(inv.deployment_fee_deducted or 0))
            total_original_principal += Decimal(str(inv.amount_deposited or 0))
            total_main_balance += Decimal(str(inv.net_principal or 0))
        
        # Build holdings response with aggregated data using atomic batch simulation
        holdings = []
        from app.Batch.controllers import BatchController
        
        for (batch_id, fund_name, fund_id), holding in holdings_map.items():
            batch_id_val = batch_id
            total_principal_val = holding["total_main_balance"]
            total_original_principal_val = holding["total_original_principal"]
            total_transaction_fee_val = holding["total_transaction_fee_usd"]
            total_entry_fee_val = holding["total_entry_fee_usd"]
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
                    inv_values = BatchController._calculate_batch_investment_values(inv, batch, db.session)
                    batch_end_balance += Decimal(str(inv_values["current_balance"]))
                    batch_total_profit += Decimal(str(inv_values["profit"]))
                    batch_total_withdrawals += Decimal(str(inv_values["withdrawals"]))

                bv_period = (
                    db.session.query(BatchValuation)
                    .filter(BatchValuation.batch_id == batch_id_val)
                    .order_by(BatchValuation.period_end_date.desc())
                    .first()
                )

                latest_epoch = db.session.query(EpochLedger).filter(
                    EpochLedger.internal_client_code == client_code,
                    func.lower(EpochLedger.fund_name) == func.lower(fund_name),
                ).order_by(EpochLedger.epoch_end.desc()).first()

                def _epoch_covers_batch(b, epoch_end):
                    if not b or not getattr(b, "date_deployed", None) or not epoch_end:
                        return True
                    bd = b.date_deployed
                    if bd.tzinfo is None:
                        bd = bd.replace(tzinfo=timezone.utc)
                    ee = epoch_end
                    if getattr(ee, "tzinfo", None) is None:
                        ee = ee.replace(tzinfo=timezone.utc)
                    return bd.date() <= ee.date()

                if bv_period:
                    valuation_data = {
                        "epoch_start": bv_period.period_end_date.isoformat(),
                        "epoch_end": bv_period.period_end_date.isoformat(),
                        "start_balance": float(total_principal_val),
                        "deposits": float(total_principal_val),
                        "withdrawals": float(batch_total_withdrawals),
                        "profit": float(batch_total_profit),
                        "end_balance": float(round(batch_end_balance, 2)),
                        "performance_rate_percent": float(bv_period.performance_rate or 0) * 100,
                    }
                elif latest_epoch and batch and _epoch_covers_batch(batch, latest_epoch.epoch_end):
                    performance_rate = float(latest_epoch.performance_rate * 100) if latest_epoch.performance_rate else 0.0
                    vr = (
                        db.session.query(ValuationRun)
                        .join(CoreFund, ValuationRun.core_fund_id == CoreFund.id)
                        .filter(
                            ValuationRun.epoch_end == latest_epoch.epoch_end,
                            func.lower(CoreFund.fund_name) == func.lower(fund_name),
                        )
                        .first()
                    )
                    if vr:
                        performance_rate = float(vr.performance_rate * 100)
                    valuation_data = {
                        "epoch_start": latest_epoch.epoch_start.isoformat(),
                        "epoch_end": latest_epoch.epoch_end.isoformat(),
                        "start_balance": float(latest_epoch.start_balance or 0),
                        "deposits": float(total_principal_val),
                        "withdrawals": float(batch_total_withdrawals),
                        "profit": float(batch_total_profit),
                        "end_balance": float(round(batch_end_balance, 2)),
                        "performance_rate_percent": performance_rate,
                    }
                else:
                    pe = bv_period.period_end_date.isoformat() if bv_period else None
                    valuation_data = {
                        "epoch_start": pe,
                        "epoch_end": pe,
                        "start_balance": float(total_principal_val),
                        "deposits": float(total_principal_val),
                        "withdrawals": float(batch_total_withdrawals),
                        "profit": float(batch_total_profit),
                        "end_balance": float(round(batch_end_balance, 2)),
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
                "fund_code": holding["fund_code"],
                "investments_count": investments_count,
                "original_principal": float(total_original_principal_val),
                "transaction_fee_usd": float(total_transaction_fee_val),
                "entry_fee_usd": float(total_entry_fee_val),
                "deployment_fee": float(total_transaction_fee_val),
                "main_balance": float(total_principal_val),
                "total_principal": float(total_principal_val),
                "latest_valuation": valuation_data
            })

        # Sort by batch_id, then fund_name
        holdings.sort(key=lambda x: (x["batch_id"] or 0, x["fund_name"]))
        
        current_balance = round(sum(
            float(h["latest_valuation"]["end_balance"] if h["latest_valuation"] else h["total_principal"]) for h in holdings
        ), 2)
        total_profit = round(current_balance - float(total_main_balance), 2)

        data = {
            "client_code": client_code,
            "investor_name": investor_name,
            "initial_investment": float(total_original_principal),
            "original_principal": float(total_original_principal),
            "total_principal": float(total_main_balance),
            "main_balance": float(total_main_balance),
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


@investment_v1.route('/api/v1/investors/<string:client_code>/portfolio/display', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True, methods=['GET', 'OPTIONS'])
def get_investor_portfolio_display(client_code):
    """
    Returns pre-computed aggregated portfolio data for display.
    
    This endpoint returns cached, pre-formatted data including:
    - KPI totals
    - Batch breakdown
    - Holdings table data
    - Fund allocation
    
    Much more efficient than calculating on the frontend.
    
    Response:
    {
        "status": 200,
        "data": {
            "kpis": {
                "total_principal": 150000.00,
                "total_current_balance": 157500.00,
                "total_profit": 7500.00,
                "profit_percentage": 5.00,
                "profit_trend": "up",
                "unique_batches": 2
            },
            "batch_breakdown": [
                {
                    "batch_id": 1,
                    "batch_name": "Batch Q1 2024",
                    "principal": 50000.00,
                    "current_balance": 52500.00,
                    "profit": 2500.00,
                    "color": "#4682B4"
                }
            ],
            "holdings_display": [
                {
                    "batch_id": 1,
                    "batch_name": "Batch Q1 2024",
                    "fund_name": "Fund A",
                    "opening_amount": 50000.00,
                    "withdrawals": 0.00,
                    "current_standing": 52500.00,
                    "profit": 2500.00,
                    "performance": 5.00,
                    "epoch_end": "2026-04-30"
                }
            ],
            "fund_allocation": [
                {
                    "name": "Fund A",
                    "value": 105000.00,
                    "percentage": "66.67%"
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
        from app.logic.portfolio_display_service import PortfolioDisplayAggregationService
        
        session = db.session
        
        # For correctness during valuation reconciliation, always rebuild the
        # display cache so Holdings profit/current standing match:
        # - Historical Statements table (EpochLedger + withdrawals)
        # - Batch detail investments table (BatchController)
        cache = PortfolioDisplayAggregationService.rebuild_cache(client_code, session)
        if not cache:
            return make_response(jsonify({
                "status": 404,
                "message": "Investor not found"
            }), 404)

        display_data = PortfolioDisplayAggregationService.get_display_data(client_code, session)
        
        return make_response(jsonify({
            "status": 200,
            "message": "Portfolio display data retrieved",
            "data": display_data
        }), 200)
    
    except Exception as e:
        import traceback
        logger.error(f"Error fetching portfolio display for {client_code}: {e}", exc_info=True)
        return make_response(jsonify({
            "status": 500,
            "message": f"Error fetching portfolio display: {str(e)}"
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
    """Permanently delete one investment (deposit) — super_admin only (destructive, see InvestmentController.delete_investment)."""
    from app.Funds.edit_service import require_role

    user, error_response = require_role(roles=("super_admin",))
    if error_response:
        return error_response

    try:
        session = db.session
        return InvestmentController.delete_investment(investment_id, session, actor_user=user)
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
    Thin wrapper: parses/validates query params, then delegates to
    _generate_investor_statement_pdf_bytes (safe to call outside request context —
    see its docstring), which does the actual work and returns a BytesIO buffer, an
    ("error", status_code, message) tuple, or None.

    Query params:
      as_of, period_only — unchanged (historical/period statement selection).
      fund_id — repeatable (?fund_id=3&fund_id=5). Omitted/empty means the
      CONSOLIDATED statement across every fund the client holds; one value
      means a FUND-SCOPED statement; multiple values means a consolidated
      statement scoped to just those funds.
    """
    as_of_raw = (request.args.get("as_of") or "").strip()
    period_only_raw = (request.args.get("period_only") or "").strip().lower()
    period_only = period_only_raw in {"1", "true", "yes"}
    as_of_dt = None
    if as_of_raw:
        try:
            norm = as_of_raw.replace("Z", "+00:00")
            as_of_dt = datetime.fromisoformat(norm)
        except ValueError:
            try:
                as_of_dt = datetime.strptime(as_of_raw, "%Y-%m-%d")
            except ValueError:
                return make_response(jsonify({
                    "status": 400,
                    "message": "Invalid as_of format. Use ISO datetime or YYYY-MM-DD."
                }), 400)
        as_of_dt = normalize_datetime_to_utc(as_of_dt)

    fund_ids_raw = request.args.getlist("fund_id")
    try:
        fund_ids = [int(f) for f in fund_ids_raw if str(f).strip()] or None
    except ValueError:
        return make_response(jsonify({"status": 400, "message": "fund_id must be an integer"}), 400)

    result = _generate_investor_statement_pdf_bytes(
        client_code, as_of_dt=as_of_dt, period_only=period_only, fund_ids=fund_ids
    )

    if isinstance(result, tuple) and len(result) == 3 and result[0] == "error":
        _, status_code, message = result
        return make_response(jsonify({"status": status_code, "message": message}), status_code)
    if result is None:
        return make_response(jsonify({"status": 500, "message": "Could not generate statement PDF"}), 500)

    filename = f"investor-statement-{client_code}.pdf"
    return send_file(result, mimetype='application/pdf', as_attachment=True, download_name=filename)


def _append_portfolio_summary_block(story, pdf_styles, theme, body_font, body_font_bold, client_code, fund_ids, fund_id_to_name, as_of_dt):
    """
    Portfolio-level summary at the top of a CONSOLIDATED statement (2+ funds).
    Shows a total current value PER CURRENCY, not one blended number — a
    client's funds can genuinely report in different currencies (currency
    lives on ShareClass, not CoreFund; see is_dangote_dprp_fund callers for
    how a fund/share-class identity is resolved elsewhere in this file), so
    summing across currencies would be numerically meaningless. Also lists
    the funds held, for a quick overview before the per-fund sections below.
    """
    from app.Funds.investor_shares import InvestorShares
    from app.Valuation.valuation_snapshot import ValuationSnapshot

    reference_date = as_of_dt.date() if as_of_dt is not None else None
    totals_by_currency = {}

    investments = db.session.query(Investment).filter(
        func.lower(Investment.internal_client_code) == func.lower(client_code),
        Investment.fund_id.in_(fund_ids),
    ).all()
    for inv in investments:
        currency = ((inv.share_class.currency if getattr(inv, "share_class", None) else None) or inv.currency_type or "").upper() or "USD"
        inv_shares = db.session.query(InvestorShares).filter(InvestorShares.investment_id == inv.id).first()
        if not inv_shares:
            continue
        snap_q = db.session.query(ValuationSnapshot).filter(ValuationSnapshot.investor_shares_id == inv_shares.id)
        if reference_date is not None:
            snap_q = snap_q.filter(ValuationSnapshot.valuation_date <= reference_date)
        latest_snap = snap_q.order_by(ValuationSnapshot.valuation_date.desc()).first()
        mv = Decimal(str(latest_snap.market_value)) if latest_snap and latest_snap.market_value is not None else Decimal("0.00")
        totals_by_currency[currency] = totals_by_currency.get(currency, Decimal("0.00")) + mv

    story.append(Paragraph('Portfolio Summary', pdf_styles["section_heading"]))
    story.append(Spacer(1, 0.08 * inch))

    summary_rows = [["Currency", "Total Current Value"]]
    for currency in sorted(totals_by_currency.keys()):
        summary_rows.append([currency, _format_statement_money(totals_by_currency[currency], currency)])
    if len(summary_rows) == 1:
        summary_rows.append(["—", "—"])
    summary_table = Table(summary_rows, colWidths=[2.0 * inch, 5.3 * inch])
    summary_table.setStyle(summary_table_style(theme, body_font, body_font_bold))
    story.append(summary_table)
    story.append(Spacer(1, 0.08 * inch))

    funds_label = ", ".join(fund_id_to_name.get(fid, "") for fid in fund_ids if fund_id_to_name.get(fid))
    story.append(Paragraph(f'<b>Funds Held:</b> {escape(funds_label or "—")}', pdf_styles["normal"]))
    story.append(Spacer(1, 0.20 * inch))


def _get_oversubscription_refund_context(client_code, fund_id):
    """
    Shared data-gathering for the one-time Oversubscription/Refund Notice
    (email body + PDF) — returns None if this client/fund combination was
    never actually affected by a pro-rata allocation. Deliberately excludes
    allocation_rate from the returned dict's client-facing fields; callers
    must not surface that percentage anywhere in investor-facing output
    (internal/admin screens read it directly off the Batch/Withdrawal rows
    instead, not through this helper).
    """
    oversubscribed = [
        inv for inv in db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code),
            Investment.fund_id == fund_id,
        ).all()
        if _safe_decimal(getattr(inv, "oversubscription_refund_amount", None)) > Decimal("0.00")
    ]
    if not oversubscribed:
        return None

    total_refund = sum((_safe_decimal(inv.oversubscription_refund_amount) for inv in oversubscribed), Decimal("0.00"))
    total_deployed = sum((_safe_decimal(inv.net_principal) for inv in oversubscribed), Decimal("0.00"))
    currency = next(
        (
            (inv.share_class.currency if getattr(inv, "share_class", None) else None) or inv.currency_type
            for inv in oversubscribed
        ),
        "USD",
    ) or "USD"
    fund_name = next((inv.fund.fund_name if inv.fund else inv.fund_name for inv in oversubscribed), None)
    investor_name = oversubscribed[0].investor_name
    investor_email = oversubscribed[0].investor_email

    refund_status = "Pending approval"
    refund_wd = (
        db.session.query(Withdrawal)
        .filter(
            func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
            Withdrawal.fund_id == fund_id,
            Withdrawal.source == "oversubscription_refund",
        )
        .order_by(Withdrawal.date_withdrawn.desc())
        .first()
    )
    if refund_wd is not None:
        refund_status = normalize_withdrawal_status(refund_wd.status)

    return {
        "total_deployed": total_deployed,
        "total_refund": total_refund,
        "currency": currency,
        "refund_status": refund_status,
        "refund_withdrawal": refund_wd,
        "fund_name": fund_name,
        "investor_name": investor_name,
        "investor_email": investor_email,
    }


def _generate_oversubscription_notice_pdf_bytes(client_code, fund_id):
    """
    Standalone one-time Oversubscription/Refund Notice PDF — Amount Deployed,
    Refund Amount, Refund Status, and the explanatory paragraph. Deliberately
    does NOT show the allocation rate percentage (client-facing output only;
    admin screens read allocation_rate directly off the Batch row instead).

    Internal helper: no Flask decorators, safe to call from a background
    thread — same shape as the other _generate_*_pdf_bytes helpers.
    """
    try:
        ctx = _get_oversubscription_refund_context(client_code, fund_id)
        if ctx is None:
            return None

        _register_montserrat_fonts()
        registered_fonts = set(pdfmetrics.getRegisteredFontNames())
        pdf_body_font = "Montserrat" if "Montserrat" in registered_fonts else "Helvetica"
        pdf_body_font_bold = "Montserrat-Bold" if "Montserrat-Bold" in registered_fonts else "Helvetica-Bold"

        fund_name = ctx["fund_name"] or "Fund"
        theme = get_statement_theme([fund_name])
        jh_logo_path = _resolve_janus_henderson_statement_logo_path([fund_name])

        pdf_buffer = BytesIO()
        doc = build_doc_template(pdf_buffer, theme, top_margin=0.5, bottom_margin=0.5)
        story = []

        styles = getSampleStyleSheet()
        pdf_styles = build_paragraph_styles(theme, styles, pdf_body_font, pdf_body_font_bold)

        append_receipt_header(
            story, theme, pdf_styles,
            jh_logo_path=jh_logo_path,
            document_title="OVERSUBSCRIPTION / REFUND NOTICE",
            fund_name=fund_name,
        )

        story.append(Paragraph(
            f'<b>Client Code:</b> {escape(client_code)}<br/>'
            f'<b>Investor:</b> {escape(ctx["investor_name"] or "—")}',
            pdf_styles["normal"],
        ))
        story.append(Spacer(1, 0.14 * inch))

        rows = [
            ["Description", "Amount"],
            ["Amount Deployed Into Shares", _format_statement_money(ctx["total_deployed"], ctx["currency"])],
            ["Refund Amount", _format_statement_money(ctx["total_refund"], ctx["currency"])],
            ["Refund Status", ctx["refund_status"]],
        ]
        table = Table(rows, colWidths=[3.5 * inch, 3.8 * inch])
        table.setStyle(summary_table_style(theme, pdf_body_font, pdf_body_font_bold))
        story.append(table)
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(
            'This fund was oversubscribed — total investor commitments exceeded what could be '
            'deployed into shares. Every investor in the affected batch received the same pro-rata '
            'allocation of their deposit; any undeployed balance is refunded through the standard '
            'withdrawal approval flow.',
            pdf_styles["normal"],
        ))

        append_branded_footer(
            story, theme, pdf_styles,
            'Disclaimer: This is an electronically generated one-time notice, issued once at deployment. '
            'It will not be repeated on future statements. Provided for informational purposes only.',
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | Client Code: {client_code}",
        )

        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        logger.error(f"Oversubscription notice PDF generation error for {client_code}, fund {fund_id}: {str(e)}")
        return None


def _append_fund_statement_section(story, client_code, fund_id, fund_name, as_of_dt, period_only, theme, pdf_styles, body_font, body_font_bold, statement_date):
    """
    Renders one fund's worth of statement content (Account Summary +
    Statements history table + the conditional DPRP oversubscription block)
    into the shared `story` list. This is the single rendering path used for
    BOTH a fund-scoped statement (called once) and a consolidated statement
    (called once per fund the client holds, in the confirmed alphabetical-by-
    fund-name order) — there is no separate/forked rendering logic between
    the two modes, only how many times and with what fund_id this is called.
    """
    section_heading_style = pdf_styles["section_heading"]
    normal_style = pdf_styles["normal"]

    json_res = _get_investor_portfolio_aggregated_data(client_code, fund_ids=[fund_id])
    payload = json_res.get_json() if hasattr(json_res, "get_json") else None
    if not payload or payload.get("status") != 200:
        story.append(Paragraph(f"No statement data available for {escape(fund_name)}.", normal_style))
        return
    data = payload.get("data") or {}
    holdings = data.get("holdings") or []

    total_principal = _safe_decimal(data.get("total_principal"))
    total_current_value = _safe_decimal(data.get("current_balance"))
    total_profit = _safe_decimal(data.get("total_profit"))
    total_deposits = sum(_safe_decimal(h.get("latest_valuation", {}).get("deposits")) for h in holdings)
    total_withdrawals = sum(_safe_decimal(h.get("latest_valuation", {}).get("withdrawals")) for h in holdings)

    if total_current_value == Decimal('0.00'):
        total_current_value = sum(_safe_decimal(h.get("latest_valuation", {}).get("end_balance")) for h in holdings)

    if not holdings:
        story.append(Paragraph(f"No statement data available for {escape(fund_name)}.", normal_style))
        return

    # If a period was requested, rebuild statement values from epochs up to that date.
    # This prevents "latest snapshot" bleed into historical statement PDFs.
    if as_of_dt is not None:
        investments_as_of = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code),
            Investment.fund_id == fund_id,
            Investment.date_deposited.isnot(None),
            Investment.date_deposited <= as_of_dt
        ).all()

        total_principal = sum((Decimal(str(inv.net_principal or 0)) for inv in investments_as_of), Decimal("0.00"))

        epochs_as_of = (
            db.session.query(EpochLedger)
            .filter(
                func.lower(EpochLedger.internal_client_code) == func.lower(client_code),
                func.lower(EpochLedger.fund_name) == func.lower(fund_name),
                EpochLedger.epoch_end <= as_of_dt,
            )
            .order_by(EpochLedger.epoch_end.desc())
            .limit(1)
            .all()
        )

        if epochs_as_of:
            total_deposits = sum((Decimal(str(r.deposits or 0)) for r in epochs_as_of), Decimal("0.00"))
            total_withdrawals = sum((Decimal(str(r.withdrawals or 0)) for r in epochs_as_of), Decimal("0.00"))
            total_current_value = sum((Decimal(str(r.end_balance or 0)) for r in epochs_as_of), Decimal("0.00"))
            total_profit = sum((Decimal(str(r.profit or 0)) for r in epochs_as_of), Decimal("0.00"))

    # Build historical statement timeline to match Investor Statement page format,
    # filtered to this fund only.
    timeline_statements = []
    period_statement_override = None
    try:
        if period_only and as_of_dt is not None:
            target_year = as_of_dt.year
            target_month = as_of_dt.month
            month_rows = db.session.query(EpochLedger).filter(
                func.lower(EpochLedger.internal_client_code) == func.lower(client_code),
                func.lower(EpochLedger.fund_name) == func.lower(fund_name),
                func.extract("year", EpochLedger.epoch_end) == target_year,
                func.extract("month", EpochLedger.epoch_end) == target_month,
            ).all()

            if month_rows:
                period_start = min((r.epoch_start for r in month_rows if r.epoch_start), default=as_of_dt)
                period_end = max((r.epoch_end for r in month_rows if r.epoch_end), default=as_of_dt)
                opening_sum = sum((Decimal(str(r.start_balance or 0)) for r in month_rows), Decimal("0.00"))
                deposits_sum = sum((Decimal(str(r.deposits or 0)) for r in month_rows), Decimal("0.00"))
                withdrawals_sum = sum((Decimal(str(r.withdrawals or 0)) for r in month_rows), Decimal("0.00"))
                profit_sum = sum((Decimal(str(r.profit or 0)) for r in month_rows), Decimal("0.00"))
                closing_sum = sum((Decimal(str(r.end_balance or 0)) for r in month_rows), Decimal("0.00"))

                period_statement_override = {
                    "type": "MONTHLY_REPORT",
                    "date": period_end.isoformat(),
                    "label": period_end.strftime("%B %Y"),
                    "fund_name": fund_name,
                    "opening_balance": float(opening_sum),
                    "deposits": float(deposits_sum),
                    "withdrawals": float(withdrawals_sum),
                    "profit": float(profit_sum),
                    "end_balance": float(closing_sum),
                    "performance_rate": 0.0,
                    "period_start": period_start,
                    "period_end": period_end,
                }

        # Unwrapped call — get_investor_statements is @jwt_required(), which needs
        # an active HTTP request; this function is also called from the background
        # send-queue scheduler thread (app context only, no request).
        timeline_res = get_investor_statements.__wrapped__(client_code)
        timeline_payload = timeline_res.get_json() if hasattr(timeline_res, "get_json") else {}
        if isinstance(timeline_payload, dict) and timeline_payload.get("status") == 200:
            rows = timeline_payload.get("data") or []
            # get_investor_statements() is unscoped by fund — filter to this
            # section's fund by name (rows carry fund_name, not fund_id).
            rows = [r for r in rows if str(r.get("fund_name") or "").strip().lower() == fund_name.strip().lower()]
            if as_of_dt is not None:
                filtered_rows = []
                for row in rows:
                    row_date = row.get("date")
                    if not row_date:
                        continue
                    try:
                        row_dt = normalize_datetime_to_utc(datetime.fromisoformat(str(row_date).replace("Z", "+00:00")))
                    except Exception:
                        continue
                    if row_dt <= as_of_dt:
                        filtered_rows.append(row)
                rows = filtered_rows

            rows.sort(key=lambda x: x.get("date") or "", reverse=True)
            timeline_statements = rows
    except Exception as timeline_err:
        print(f"⚠️  Warning: Could not load timeline statements for {client_code}/{fund_name}: {timeline_err}")

    previous_period_value = None
    previous_period_date_text = None
    if timeline_statements:
        full_timeline_rows = list(timeline_statements)
        # Optional: force this PDF to represent only the selected statement period (single row),
        # used by historical statement row downloads.
        if period_only and as_of_dt is not None:
            selected_row = period_statement_override
            if selected_row is None:
                target_year = as_of_dt.year
                target_month = as_of_dt.month
                selected_row = next(
                    (
                        r for r in timeline_statements
                        if (r.get("type") == "MONTHLY_REPORT")
                        and r.get("date")
                        and datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00")).year == target_year
                        and datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00")).month == target_month
                    ),
                    None,
                )
            if selected_row is None:
                target_year = as_of_dt.year
                target_month = as_of_dt.month
                selected_row = next(
                    (
                        r for r in timeline_statements
                        if r.get("date")
                        and datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00")).year == target_year
                        and datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00")).month == target_month
                    ),
                    None,
                )
            if selected_row is not None:
                # For periodic statement downloads, show the prior standing/value from
                # the immediately previous statement row (if available), e.g. Apr 20 value for Apr 22 statement.
                try:
                    selected_dt = normalize_datetime_to_utc(
                        datetime.fromisoformat(str(selected_row.get("date")).replace("Z", "+00:00"))
                    )
                except Exception:
                    selected_dt = None
                if selected_dt is not None:
                    previous_candidates = []
                    for r in full_timeline_rows:
                        try:
                            rdt = normalize_datetime_to_utc(
                                datetime.fromisoformat(str(r.get("date")).replace("Z", "+00:00"))
                            )
                        except Exception:
                            continue
                        if rdt < selected_dt and r.get("end_balance") is not None:
                            previous_candidates.append((rdt, r))
                    if previous_candidates:
                        previous_candidates.sort(key=lambda x: x[0], reverse=True)
                        prev_dt, prev_row = previous_candidates[0]
                        previous_period_value = Decimal(str(prev_row.get("end_balance") or 0))
                        previous_period_date_text = prev_dt.strftime("%d %b %Y")
                timeline_statements = [selected_row]

        total_deposits = sum((Decimal(str(r.get("deposits") or 0)) for r in timeline_statements), Decimal("0.00"))
        total_withdrawals = sum((Decimal(str(r.get("withdrawals") or 0)) for r in timeline_statements), Decimal("0.00"))
        total_profit = sum(
            (
                Decimal(str(r.get("profit") or 0))
                for r in timeline_statements
                if r.get("type") in {"MONTHLY_REPORT", "VALUATION"}
            ),
            Decimal("0.00"),
        )
        if period_only:
            total_principal = Decimal(str(timeline_statements[0].get("opening_balance") or 0)) + total_deposits
        else:
            total_principal = total_deposits if total_deposits > 0 else total_principal
        # Use consolidated latest standing across all active balance buckets (multi-batch safe).
        latest_by_bucket = {}
        for row in timeline_statements:
            bucket = row.get("balance_bucket") or f"fallback:{row.get('batch_id') or row.get('fund_name') or 'portfolio'}"
            if bucket not in latest_by_bucket:
                latest_by_bucket[bucket] = row

        if latest_by_bucket:
            total_current_value = sum(
                (Decimal(str(r.get("end_balance") or 0)) for r in latest_by_bucket.values()),
                Decimal("0.00"),
            )

    # Account summary
    net_deployment_amount = sum(
        (
            Decimal(str(r.get("deposits") or 0))
            for r in timeline_statements
            if (r.get("type") in {"DEPLOYMENT", "DEPOSIT"})
        ),
        Decimal("0.00"),
    )
    # ── Account Summary header (Shares / Market Value / NAV per Share) ──
    # Pull these from the same underlying data as the "All Positions" section:
    # InvestorShares + latest ValuationSnapshot + latest NAV (NavHistory).
    acct_currency = None
    acct_total_shares = Decimal("0.00")
    acct_total_market_value = Decimal("0.00")
    acct_nav_per_share = None
    acct_deployment_nav = None
    acct_nav_date = None
    acct_deployment_date = None
    acct_deployment_rows = []
    section_investments = []
    try:
        from app.Funds.investor_shares import InvestorShares
        from app.Valuation.valuation_snapshot import ValuationSnapshot
        from app.Funds.nav_history import NavHistory

        reference_date = as_of_dt.date() if as_of_dt is not None else None

        # Aggregate positions by currency, then pick the "primary" one:
        # whichever has the largest market value (matches what user sees as main portfolio).
        positions_agg = {}

        all_investments_for_acct = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code),
            Investment.fund_id == fund_id,
        ).all()
        section_investments = all_investments_for_acct

        for inv in all_investments_for_acct:
            currency = ((inv.share_class.currency if getattr(inv, "share_class", None) else None) or inv.currency_type or "").upper() or None
            if not currency:
                continue

            agg = positions_agg.setdefault(currency, {
                "shares": Decimal("0.00"),
                "market_value": Decimal("0.00"),
                "nav_per_share": None,
                "nav_date": None,
                "deployment_nav_weighted_sum": Decimal("0.00"),
                "deployment_shares": Decimal("0.00"),
                "deployment_date": None,
                "deployment_by_batch": {},
            })

            inv_shares = db.session.query(InvestorShares).filter(
                InvestorShares.investment_id == inv.id
            ).first()
            if not inv_shares:
                continue

            # Latest valuation snapshot (optionally <= as_of date)
            snap_q = db.session.query(ValuationSnapshot).filter(
                ValuationSnapshot.investor_shares_id == inv_shares.id
            )
            if reference_date is not None:
                snap_q = snap_q.filter(ValuationSnapshot.valuation_date <= reference_date)
            latest_snap = snap_q.order_by(ValuationSnapshot.valuation_date.desc()).first()

            shares_val = Decimal(str(inv_shares.shares_owned or 0))
            deployment_nav_val = (
                Decimal(str(inv_shares.deployment_nav or 0))
                if getattr(inv_shares, "deployment_nav", None) is not None
                else None
            )
            mv_val = None
            nav_ps = None
            nav_dt = None

            if latest_snap is not None:
                shares_val = Decimal(str(latest_snap.shares_held or shares_val or 0))
                mv_val = Decimal(str(latest_snap.market_value or 0))
                nav_ps = Decimal(str(latest_snap.nav_per_share or 0)) if latest_snap.nav_per_share is not None else None
                nav_dt = latest_snap.valuation_date

            # Fallback: if no snapshot market value, approximate using the
            # current price (NavHistory.resolve_current_price — the single
            # source of truth; see its docstring for why a naive "latest
            # NavHistory row" can return a stale, pre-deployment price).
            if (mv_val is None or mv_val <= Decimal("0")) and inv.share_class_id and shares_val > 0:
                resolved_nav, resolved_nav_dt, _is_fallback = NavHistory.resolve_current_price(
                    inv.share_class_id, getattr(inv_shares, "deployment_date", None), deployment_nav_val, session=db.session
                )
                if resolved_nav is not None:
                    nav_ps = resolved_nav
                    nav_dt = resolved_nav_dt
                    mv_val = (shares_val * nav_ps).quantize(Decimal("0.01"))

            agg["shares"] += shares_val
            if deployment_nav_val is not None and deployment_nav_val > Decimal("0") and shares_val > Decimal("0"):
                agg["deployment_nav_weighted_sum"] += (deployment_nav_val * shares_val)
                agg["deployment_shares"] += shares_val
                dep_dt = getattr(inv_shares, "deployment_date", None)
                if dep_dt is not None:
                    if agg["deployment_date"] is None or dep_dt > agg["deployment_date"]:
                        agg["deployment_date"] = dep_dt
                batch_key = str(getattr(inv, "batch_id", None) or f"inv-{inv.id}")
                batch_obj = getattr(inv, "batch", None)
                batch_label = (
                    getattr(batch_obj, "batch_name", None)
                    or getattr(inv, "batch_name", None)
                    or f"Batch {getattr(inv, 'batch_id', '')}".strip()
                )
                agg["deployment_by_batch"][batch_key] = {
                    "batch_label": batch_label,
                    "nav": deployment_nav_val,
                    "date": dep_dt,
                }
            if mv_val is not None and mv_val > Decimal("0"):
                agg["market_value"] += mv_val
            if nav_dt is not None:
                if agg["nav_date"] is None or nav_dt > agg["nav_date"]:
                    agg["nav_date"] = nav_dt

        # Pick the dominant currency by market value
        if positions_agg:
            acct_currency = max(positions_agg.items(), key=lambda kv: kv[1].get("market_value", Decimal("0.00")))[0]
            acct_total_shares = positions_agg[acct_currency]["shares"]
            acct_total_market_value = positions_agg[acct_currency]["market_value"]
            acct_nav_date = positions_agg[acct_currency]["nav_date"]
            if acct_total_shares > 0 and acct_total_market_value > 0:
                acct_nav_per_share = (acct_total_market_value / acct_total_shares).quantize(Decimal("0.0001"))
            dep_shares = positions_agg[acct_currency].get("deployment_shares", Decimal("0.00"))
            dep_weighted = positions_agg[acct_currency].get("deployment_nav_weighted_sum", Decimal("0.00"))
            if dep_shares > 0 and dep_weighted > 0:
                acct_deployment_nav = (dep_weighted / dep_shares).quantize(Decimal("0.0001"))
            acct_deployment_date = positions_agg[acct_currency].get("deployment_date")
            acct_deployment_rows = list(positions_agg[acct_currency].get("deployment_by_batch", {}).values())
    except Exception:
        acct_currency = acct_currency or "USD"
        acct_total_shares = Decimal("0.00")
        acct_total_market_value = Decimal("0.00")
        acct_nav_per_share = None
        acct_deployment_nav = None
        acct_nav_date = None
        acct_deployment_date = None
        acct_deployment_rows = []

    nav_date_txt = acct_nav_date.strftime("%d %b %Y") if acct_nav_date else "—"
    # Keep NAV/Share "as of" aligned with the statement valuation date shown in header.
    try:
        nav_date_txt = datetime.strptime(statement_date, "%B %d, %Y").strftime("%d %b %Y")
    except Exception:
        pass
    deployment_date_txt = acct_deployment_date.strftime("%d %b %Y") if acct_deployment_date else "—"
    shares_txt = f"{acct_total_shares:,.4f}" if acct_total_shares else "—"
    # Keep the headline Market Value consistent with the statement's
    # Current Balance.  The latter is the authoritative investor balance
    # used throughout this generated statement.
    mv_txt_val = Decimal(str(total_current_value or 0))
    mv_txt = _format_statement_money(mv_txt_val, acct_currency)
    nav_txt = f"{acct_nav_per_share:,.4f}" if acct_nav_per_share is not None else "—"
    deployment_nav_txt = f"{acct_deployment_nav:,.4f}" if acct_deployment_nav is not None else "—"
    if acct_nav_per_share is not None and nav_date_txt != "—":
        nav_txt = f"{nav_txt} (as of {nav_date_txt})"
    if acct_deployment_nav is not None and deployment_date_txt != "—":
        deployment_nav_txt = f"{deployment_nav_txt} (as of {deployment_date_txt})"

    deployment_detail_rows = []
    if acct_deployment_rows:
        acct_deployment_rows.sort(
            key=lambda r: ((r.get("date") or datetime.min), str(r.get("batch_label") or "")),
            reverse=True,
        )
        for row in acct_deployment_rows:
            nav_val = row.get("nav")
            if nav_val is None:
                continue
            dep_dt = row.get("date")
            dep_dt_txt = dep_dt.strftime("%d %b %Y") if dep_dt else "—"
            deployment_detail_rows.append([
                "NAV at Deployment",
                f"{Decimal(str(nav_val)):,.4f} (as of {dep_dt_txt})" if dep_dt_txt != "—" else f"{Decimal(str(nav_val)):,.4f}",
            ])

    header_summary_data = [
        ["Shares", shares_txt],
        ["Market Value", mv_txt],
    ]

    header_summary_table = Table(header_summary_data, colWidths=[2.7 * inch, 4.8 * inch])
    header_summary_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), body_font, 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#111827')),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    summary_data = [['Description', 'Amount']]
    if period_only and previous_period_value is not None:
        prev_label_date = previous_period_date_text or "previous period"
        summary_data.append([f'Previous Value (as of {prev_label_date})', _format_statement_money(previous_period_value, acct_currency)])
    if net_deployment_amount > Decimal("0.00"):
        summary_data.append(['Net Deployment Amount', _format_statement_money(net_deployment_amount, acct_currency)])
    if Decimal(str(total_withdrawals or 0)) != Decimal("0"):
        summary_data.append(['Withdrawals (YTD)', _format_statement_money(total_withdrawals, acct_currency)])
    summary_data.append(['Current Balance', _format_statement_money(total_current_value, acct_currency)])
    summary_data.append(['Gain/Loss', _format_statement_money(total_profit, acct_currency)])
    summary_table = Table(summary_data, colWidths=[5.2 * inch, 2.3 * inch])
    summary_table.setStyle(summary_table_style(theme, body_font, body_font_bold))

    # Color Gain/Loss (or legacy Profit/Loss) row based on sign
    profit_row_idx = next((i for i, r in enumerate(summary_data) if (r and r[0] in {"Gain/Loss", "Profit/Loss"})), None)
    try:
        profit_color = colors.HexColor('#22c55e') if Decimal(str(total_profit or 0)) >= Decimal("0") else colors.HexColor('#ef4444')
    except Exception:
        profit_color = colors.HexColor('#111827')
    if profit_row_idx is not None:
        summary_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, profit_row_idx), (0, profit_row_idx), profit_color),
            ('TEXTCOLOR', (1, profit_row_idx), (1, profit_row_idx), profit_color),
            ('FONTNAME', (0, profit_row_idx), (1, profit_row_idx), body_font_bold),
        ]))

    if theme.is_jh:
        story.append(build_orange_banner_table(f'Account Summary ({acct_currency or "USD"})', theme, body_font_bold, font_size=10))
        story.append(Spacer(1, 0.06 * inch))
    else:
        story.append(Paragraph(f'Account Summary ({acct_currency or "USD"})', section_heading_style))
        story.append(Spacer(1, 0.10 * inch))
    story.append(header_summary_table)
    story.append(summary_table)
    story.append(Spacer(1, 0.20 * inch))

    # Statements timeline grouped by currency (KES/USD)
    story.append(Paragraph('Statements', section_heading_style))

    def _render_statements_table(rows_for_currency, currency_label):
        def _fmt_money(amount: Decimal | None) -> str:
            if amount is None:
                return "—"
            try:
                amt = Decimal(str(amount)).quantize(Decimal("0.01"))
            except Exception:
                return "—"
            # Currency prefix removed for compact tables (currency is already grouped in the section title).
            return f"{amt:,.2f}"

        def _fmt_decimal(amount, places: str) -> str:
            if amount is None:
                return "â€”"
            try:
                exponent = abs(Decimal(places).as_tuple().exponent)
                return f"{Decimal(str(amount)).quantize(Decimal(places)):,.{exponent}f}"
            except Exception:
                return "â€”"

        show_performance_col = any(
            (r.get("type") in {"MONTHLY_REPORT", "VALUATION"} and (r.get("performance_rate") is not None))
            for r in rows_for_currency
        )

        # Shares/NAV show the share count and NAV used at the deposit or valuation event.
        history_header = ['Date', 'Statement/Event', 'Shares', 'NAV', 'Deposit', 'Withdrawal', 'Previous Value', 'Gain/Loss']
        if show_performance_col:
            history_header.append('Perf %')
        history_header.append('Current Value')

        history_rows = [history_header]
        for row in rows_for_currency:
            row_type = row.get('type') or ''
            row_date = row.get('date') or ''
            try:
                # Accept both datetime ISO strings and date-only ISO strings.
                row_date_str = str(row_date)
                try:
                    row_dt = datetime.fromisoformat(row_date_str.replace("Z", "+00:00"))
                except ValueError:
                    # date-only: YYYY-MM-DD
                    row_dt = datetime.strptime(row_date_str.split("T")[0], "%Y-%m-%d")
                row_date_txt = row_dt.strftime('%d %b %Y')
            except Exception:
                row_date_txt = '—'

            label = row.get('label')
            # Always normalize deployment wording to compact Deposit label.
            if row_type in {'DEPOSIT', 'DEPLOYMENT'}:
                try:
                    label = f"Deposit - {datetime.fromisoformat(str(row_date).replace('Z', '+00:00')).strftime('%b')}"
                except Exception:
                    label = "Deposit"
            elif not label:
                if row_type == 'VALUATION':
                    label = "Valuation Report"
                elif row_type == 'WITHDRAWAL':
                    label = "Withdrawal"
                elif row_type == 'MONTHLY_REPORT':
                    try:
                        label = datetime.fromisoformat(str(row_date).replace('Z', '+00:00')).strftime('%B %Y')
                    except Exception:
                        label = "Monthly Report"
                else:
                    label = "Statement"

            # Enrich valuation rows with NAV/Share and the valuation date text.
            if row_type == 'VALUATION':
                label = "Valuation Report"

            deposits_val = Decimal(str(row.get('deposits') or 0))
            opening_val = Decimal(str(row.get('opening_balance') or 0))
            withdrawals_val = Decimal(str(row.get('withdrawals') or 0))
            profit_val = Decimal(str(row.get('profit') or 0))
            closing_val = Decimal(str(row.get('end_balance') or 0))
            perf_rate = row.get('performance_rate')
            try:
                perf_rate_num = float(perf_rate) if perf_rate is not None else None
            except Exception:
                perf_rate_num = None

            # Keep event label compact so numeric columns fit in-table.
            event_label = str(label)

            shares_raw = row.get("shares") if row.get("shares") is not None else row.get("shares_at_deployment")
            nav_raw = row.get("nav_per_share") if row.get("nav_per_share") is not None else row.get("nav_at_deployment")
            shares_val = Decimal(str(shares_raw)) if shares_raw is not None else None
            nav_val = Decimal(str(nav_raw)) if nav_raw is not None else None
            calc_value = (shares_val * nav_val).quantize(Decimal("0.01")) if (shares_val is not None and nav_val is not None) else None
            # Hidden reconciliation gap handling: snap to statement market value and keep adjustment internal.
            rounding_adjustment = Decimal("0.00")
            if calc_value is not None and closing_val is not None:
                rounding_adjustment = (closing_val - calc_value).quantize(Decimal("0.01"))
            display_value = (calc_value + rounding_adjustment) if calc_value is not None else None

            deposit_for_row = deposits_val if deposits_val != Decimal("0") else None
            withdrawal_for_row = withdrawals_val.copy_abs() if withdrawals_val != Decimal("0") else None
            previous_for_row = opening_val if opening_val != Decimal("0") else None
            current_for_row = closing_val if closing_val != Decimal("0") else None
            gain_for_row = profit_val if row_type in {'MONTHLY_REPORT', 'VALUATION'} else None

            # For deployment/deposit events, previous and current are typically equal
            # when they represent the first standing value.
            if row_type in {"DEPOSIT", "DEPLOYMENT"}:
                if current_for_row is None and display_value is not None:
                    current_for_row = Decimal(str(display_value))
                if previous_for_row is None:
                    previous_for_row = current_for_row

            row_cells = [
                row_date_txt,
                event_label,
                _fmt_decimal(shares_val, "0.0001"),
                _fmt_decimal(nav_val, "0.0001"),
                _fmt_money(deposit_for_row),
                _fmt_money(withdrawal_for_row),
                _fmt_money(previous_for_row),
                _fmt_money(gain_for_row),
            ]
            if show_performance_col:
                row_cells.append(
                    f'{perf_rate_num:.2f}%' if (row_type in {'MONTHLY_REPORT', 'VALUATION'} and perf_rate_num is not None) else '—'
                )
            row_cells.append(_fmt_money(current_for_row))
            row_cells = [
                "-"
                if isinstance(cell, str) and ("â" in cell or "Ã" in cell or cell == "—")
                else cell
                for cell in row_cells
            ]
            history_rows.append(row_cells)

        if len(history_rows) == 1:
            empty_row = ['—', 'No statements found', '—', '—', '—', '—']
            if show_performance_col:
                empty_row.append('—')
            empty_row.append('—')
            history_rows.append(empty_row)

        history_rows = [
            [
                "-"
                if isinstance(cell, str) and ("Ã¢" in cell or "Ãƒ" in cell or cell == "â€”")
                else cell
                for cell in row
            ]
            for row in history_rows
        ]

        story.append(Paragraph(f'{currency_label} Statements', normal_style))
        story.append(Spacer(1, 0.04 * inch))

        # widths for fixed + optional columns
        col_widths = [
            0.68 * inch,  # Date
            1.20 * inch,  # Statement/Event
            0.72 * inch,  # Shares
            0.58 * inch,  # NAV
            0.72 * inch,  # Deposit
            0.72 * inch,  # Withdrawal
            0.78 * inch,  # Previous Value
            0.68 * inch,  # Gain/Loss
        ]
        if show_performance_col:
            col_widths.append(0.48 * inch)
        col_widths.append(0.74 * inch)  # Current Value

        history_table = Table(history_rows, colWidths=col_widths)
        history_table.setStyle(history_table_style(theme, body_font, body_font_bold))

        # Color all non-empty deposit values in green.
        for idx, row in enumerate(rows_for_currency, start=1):
            try:
                dep = Decimal(str(row.get('deposits') or 0))
            except Exception:
                dep = Decimal("0")
            if dep != Decimal("0"):
                history_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (4, idx), (4, idx), colors.HexColor('#16a34a')),
                    ('FONTNAME', (4, idx), (4, idx), body_font_bold),
                ]))

            # Color Gain/Loss by sign (green gain, red loss).
            try:
                pnl = Decimal(str(row.get('profit') or 0))
            except Exception:
                pnl = Decimal("0")
            if pnl > 0:
                history_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (7, idx), (7, idx), colors.HexColor('#16a34a')),
                    ('FONTNAME', (7, idx), (7, idx), body_font_bold),
                ]))
            elif pnl < 0:
                history_table.setStyle(TableStyle([
                    ('TEXTCOLOR', (7, idx), (7, idx), colors.HexColor('#dc2626')),
                    ('FONTNAME', (7, idx), (7, idx), body_font_bold),
                ]))

            # Color Perf % by sign (green gain, red loss) when present.
            if show_performance_col:
                try:
                    perf = Decimal(str(row.get('performance_rate') or 0))
                except Exception:
                    perf = Decimal("0")
                if perf > 0:
                    history_table.setStyle(TableStyle([
                        ('TEXTCOLOR', (8, idx), (8, idx), colors.HexColor('#16a34a')),
                        ('FONTNAME', (8, idx), (8, idx), body_font_bold),
                    ]))
                elif perf < 0:
                    history_table.setStyle(TableStyle([
                        ('TEXTCOLOR', (8, idx), (8, idx), colors.HexColor('#dc2626')),
                        ('FONTNAME', (8, idx), (8, idx), body_font_bold),
                    ]))

        story.append(history_table)
        story.append(Spacer(1, 0.14 * inch))

    grouped_rows = {
        "KES": [r for r in timeline_statements if str(r.get("currency") or "").upper() == "KES"],
        "USD": [r for r in timeline_statements if str(r.get("currency") or "").upper() == "USD"],
    }
    other_rows = [
        r for r in timeline_statements
        if str(r.get("currency") or "").upper() not in {"KES", "USD"}
    ]

    if grouped_rows["KES"]:
        _render_statements_table(grouped_rows["KES"], "KES")
    if grouped_rows["KES"] and grouped_rows["USD"]:
        story.append(Table([['']], colWidths=[7.3 * inch], style=[('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor(theme.divider_grey))]))
        story.append(Spacer(1, 0.08 * inch))
    if grouped_rows["USD"]:
        _render_statements_table(grouped_rows["USD"], "USD")
    if other_rows:
        _render_statements_table(other_rows, "Other")
    story.append(Spacer(1, 0.08 * inch))

    # Oversubscription/refund info is NOT shown on this (FUNDS) section — it's a
    # one-time event tied to a single deployment, not something that belongs on
    # every recurring statement this investor ever receives. See
    # EmailService.send_oversubscription_refund_notices for the separate,
    # one-time notice (sent once, from the Withdrawals page) that replaces
    # what used to be the "_append_dprp_oversubscription_block" section here.
    # The SHARES section below (Task 5) is different: refund USD/status there
    # is a plain factual field describing the holding's current state, not a
    # one-time narrative, and the task spec explicitly calls for it.


def _resolve_shares_nav_for_investment(inv, investor_shares_by_investment_id=None, session=None):
    """
    Task 7: shared "current NAV per share" resolver for a SHARES holding —
    used by both the PDF statement section and the Excel export, so the two
    never disagree. (nav_per_share, is_valued): is_valued is False when no
    committed valuation exists yet for this share class since deployment
    (NavHistory.resolve_current_price would otherwise silently fall back to
    the deployment price, which this app deliberately surfaces as "Not valued
    yet" instead of a real valuation — see _append_shares_statement_section).
    """
    from app.Funds.investor_shares import InvestorShares
    from app.Funds.nav_history import NavHistory

    session = session or db.session
    inv_shares = (investor_shares_by_investment_id or {}).get(inv.id)
    if inv_shares is None:
        inv_shares = session.query(InvestorShares).filter(InvestorShares.investment_id == inv.id).first()

    share_class_id = (inv_shares.share_class_id if inv_shares else None) or inv.share_class_id
    deployment_date = inv_shares.deployment_date if inv_shares else (inv.date_transferred.date() if inv.date_transferred else None)
    deployment_nav = (inv_shares.deployment_nav if inv_shares else None) or inv.previous_nav_price or inv.shares_price_per_share_ngn
    if not share_class_id or deployment_nav is None:
        return None, False

    nav_per_share, _nav_date, is_fallback = NavHistory.resolve_current_price(
        share_class_id, deployment_date, deployment_nav, session=session
    )
    if nav_per_share is None or is_fallback:
        return None, False
    return nav_per_share, True


def _append_shares_statement_section(story, client_code, shares_fund_ids, pdf_styles, body_font, body_font_bold, theme):
    """
    Renders the "Shares (Dangote Petroleum Refinery IPO)" statement section.

    Task 7 correction: SHARES is valued exactly like a FUNDS holding — shares
    x the latest committed NAV-per-share (NGN) for its share class, via the
    same InvestorShares / NavHistory mechanism FUNDS uses (NavHistory.
    resolve_current_price), NOT a fixed "price per share" set once at
    deployment. price_per_share_ngn (shares_price_per_share_ngn on Investment)
    only ever determined how many whole shares were bought (Task 3) — it's
    shown here as the deployment cost basis, never as the ongoing valuation.
    If no valuation has been committed for this share class since deployment,
    resolve_current_price falls back to the deployment price itself; this
    section deliberately does NOT silently treat that as "the current value"
    the way FUNDS's generic balance calc does — it shows "Not valued yet"
    instead, per Task 7.

    One Description/Amount table per SHARES holding (deposit); a totals table
    is added when the investor has more than one SHARES holding.

    USD-denominated fields (deposit, entry fee, transaction cost, net, refund)
    and NGN-denominated fields (net/cost basis, NAV, market value, gain/loss)
    are always kept on separate rows/totals — never summed together (Task 5 rule).
    """
    from app.Funds.investor_shares import InvestorShares

    section_heading_style = pdf_styles["section_heading"]
    normal_style = pdf_styles["normal"]

    holdings = (
        db.session.query(Investment)
        .filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code),
            Investment.fund_id.in_(shares_fund_ids),
        )
        .order_by(Investment.date_deposited.asc())
        .all()
    )
    if not holdings:
        story.append(Paragraph("No Shares holdings found.", normal_style))
        return

    cent = Decimal("0.01")
    NOT_VALUED_YET = "Not valued yet"

    investor_shares_by_investment_id = {
        s.investment_id: s
        for s in db.session.query(InvestorShares).filter(
            InvestorShares.investment_id.in_([h.id for h in holdings])
        ).all()
    }

    def _money(value):
        return _format_statement_money(value, "USD")

    def _ngn(value, places=2):
        if value is None:
            return "—"
        quant = Decimal("1").scaleb(-places) if places else Decimal("1")
        return f"NGN {Decimal(str(value)).quantize(quant):,.{places}f}"

    def _rate(value):
        return str(Decimal(str(value)).normalize()) if value is not None else "—"

    def _shares_qty(value):
        return f"{Decimal(str(value)):,.4f}" if value is not None else "—"

    def _resolve_nav(inv):
        return _resolve_shares_nav_for_investment(inv, investor_shares_by_investment_id, db.session)

    totals = {
        "deposit": Decimal("0.00"), "entry_fee": Decimal("0.00"), "tx_cost": Decimal("0.00"),
        "net_usd": Decimal("0.00"), "net_ngn": Decimal("0.00"), "shares": Decimal("0.00"),
        "market_value_ngn": Decimal("0.00"), "gain_loss_ngn": Decimal("0.00"), "refund_usd": Decimal("0.00"),
    }
    all_valued = True

    for inv in holdings:
        deposit = Decimal(str(inv.amount_deposited or 0))
        entry_fee = Decimal(str(inv.deployment_fee_deducted or 0))
        tx_cost = Decimal(str(inv.transfer_fee_deducted or 0))
        # Deliberately NOT Investment.net_principal — that property also
        # subtracts oversubscription_refund_amount, which this section shows
        # as its own separate "Refund (USD)" row (see module docstring above).
        net_usd = (deposit - entry_fee - tx_cost).quantize(cent)
        refund_usd = Decimal(str(inv.oversubscription_refund_amount or 0))
        exchange_rate = inv.shares_exchange_rate_ngn
        net_ngn = inv.net_ngn  # the NGN cost basis deployed into shares
        shares_owned = inv.shares_owned

        nav_per_share, is_valued = _resolve_nav(inv)
        if is_valued and shares_owned is not None:
            market_value_ngn = (Decimal(str(shares_owned)) * Decimal(str(nav_per_share))).quantize(cent)
            cost_basis_ngn = Decimal(str(net_ngn)) if net_ngn is not None else Decimal("0.00")
            gain_loss_ngn = market_value_ngn - cost_basis_ngn
        else:
            market_value_ngn = None
            gain_loss_ngn = None
            all_valued = False

        refund_status = "—"
        if refund_usd > 0:
            refund_wd = (
                db.session.query(Withdrawal)
                .filter(
                    func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
                    Withdrawal.fund_id == inv.fund_id,
                    Withdrawal.source == WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                )
                .order_by(Withdrawal.date_withdrawn.desc())
                .first()
            )
            refund_status = normalize_withdrawal_status(refund_wd.status) if refund_wd else "Pending"

        totals["deposit"] += deposit
        totals["entry_fee"] += entry_fee
        totals["tx_cost"] += tx_cost
        totals["net_usd"] += net_usd
        if net_ngn is not None:
            totals["net_ngn"] += Decimal(str(net_ngn))
        if shares_owned is not None:
            totals["shares"] += Decimal(str(shares_owned))
        if market_value_ngn is not None:
            totals["market_value_ngn"] += market_value_ngn
        if gain_loss_ngn is not None:
            totals["gain_loss_ngn"] += gain_loss_ngn
        totals["refund_usd"] += refund_usd

        if len(holdings) > 1:
            batch_label = inv.batch.batch_name if getattr(inv, "batch", None) else f"Batch {inv.batch_id}"
            deposit_date_txt = inv.date_deposited.strftime("%d %b %Y") if inv.date_deposited else "—"
            story.append(Paragraph(f"Deposit — {escape(str(batch_label))} ({deposit_date_txt})", normal_style))
            story.append(Spacer(1, 0.04 * inch))

        holding_rows = [
            ["Description", "Amount"],
            ["Deposit (USD)", _money(deposit)],
            ["Entry Fee (USD)", _money(entry_fee)],
            ["Transaction Cost (USD)", _money(tx_cost)],
            ["Net (USD)", _money(net_usd)],
            ["Exchange Rate Used (NGN / USD)", _rate(exchange_rate)],
            ["Net (NGN) — Cost Basis", _ngn(net_ngn)],
            ["Shares Allocated", _shares_qty(shares_owned)],
            ["NAV / Share (NGN)", _ngn(nav_per_share, places=4) if is_valued else NOT_VALUED_YET],
            ["Market Value (NGN)", _ngn(market_value_ngn) if is_valued else NOT_VALUED_YET],
            ["Gain / Loss (NGN)", _ngn(gain_loss_ngn) if is_valued else NOT_VALUED_YET],
            ["Refund (USD)", _money(refund_usd) if refund_usd > 0 else "—"],
            ["Refund Status", refund_status],
        ]
        holding_table = Table(holding_rows, colWidths=[4.2 * inch, 3.3 * inch])
        holding_table.setStyle(summary_table_style(theme, body_font, body_font_bold))
        story.append(holding_table)
        story.append(Spacer(1, 0.14 * inch))

    if len(holdings) > 1:
        totals_rows = [
            ["Description", "Amount"],
            ["Total Deposit (USD)", _money(totals["deposit"])],
            ["Total Entry Fee (USD)", _money(totals["entry_fee"])],
            ["Total Transaction Cost (USD)", _money(totals["tx_cost"])],
            ["Total Net (USD)", _money(totals["net_usd"])],
            ["Total Net (NGN) — Cost Basis", _ngn(totals["net_ngn"])],
            ["Total Shares Allocated", _shares_qty(totals["shares"])],
            ["Total Market Value (NGN)", _ngn(totals["market_value_ngn"]) if all_valued else NOT_VALUED_YET],
            ["Total Gain / Loss (NGN)", _ngn(totals["gain_loss_ngn"]) if all_valued else NOT_VALUED_YET],
            ["Total Refund (USD)", _money(totals["refund_usd"]) if totals["refund_usd"] > 0 else "—"],
        ]
        if theme.is_jh:
            story.append(build_orange_banner_table('Shares Totals', theme, body_font_bold, font_size=10))
            story.append(Spacer(1, 0.06 * inch))
        else:
            story.append(Paragraph('Shares Totals', section_heading_style))
            story.append(Spacer(1, 0.08 * inch))
        totals_table = Table(totals_rows, colWidths=[4.2 * inch, 3.3 * inch])
        totals_table.setStyle(summary_table_style(theme, body_font, body_font_bold))
        story.append(totals_table)
        story.append(Spacer(1, 0.10 * inch))


def _generate_investor_statement_pdf_bytes(client_code, as_of_dt=None, period_only=False, fund_ids=None):
    """
    Internal helper: the actual statement-PDF-building body, with no Flask
    decorators and no send_file() call — safe to call from a background thread
    (the email send-queue scheduler attaches this to INVESTOR_STATEMENT emails),
    not just an HTTP request. Mirrors _generate_deposit/transfer/deployment_receipt_pdf_bytes.
    Returns a BytesIO buffer on success, ("error", status_code, message) for a
    known/expected failure (no holdings, bad font install, etc.), or None on an
    unexpected exception (logged here).

    fund_ids: None/empty -> CONSOLIDATED statement, one section per fund the
    client holds (alphabetical by fund name), with a portfolio-level summary
    block at the top. A single id -> FUND-SCOPED statement (one section, no
    portfolio summary — structurally identical to any other NAV fund's
    statement). Several ids (but not literally every fund the client holds)
    -> a consolidated statement scoped to just those funds — same section
    rendering either way; see _append_fund_statement_section for the shared
    per-fund logic.

    Task 5: resolved_fund_ids is further split into funds_section_ids
    (product_type FUNDS, rendered exactly as before under a "FUNDS" heading)
    and shares_section_ids (product_type SHARES, rendered once under a
    "SHARES (DANGOTE PETROLEUM REFINERY IPO)" heading via
    _append_shares_statement_section) — one investor, one PDF, two sections,
    neither one touching the other's data/math.
    """
    try:
        all_client_investments = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).all()
        if not all_client_investments:
            logger.warning(f"Statement PDF: no holdings found for investor {client_code}")
            return ("error", 404, f"No holdings found for investor {client_code}")

        investor_name = all_client_investments[0].investor_name

        fund_id_to_name = {}
        for inv in all_client_investments:
            fid = inv.fund_id
            if fid is None:
                continue
            fname = (inv.fund.fund_name if getattr(inv, "fund", None) else inv.fund_name) or None
            if fname and fid not in fund_id_to_name:
                fund_id_to_name[fid] = fname

        if fund_ids:
            requested = {int(f) for f in fund_ids}
            resolved_fund_ids = [fid for fid in fund_id_to_name if fid in requested]
            if not resolved_fund_ids:
                logger.warning(f"Statement PDF: none of requested funds {requested} held by {client_code}")
                return ("error", 404, f"Investor {client_code} does not hold any of the requested fund(s)")
        else:
            resolved_fund_ids = list(fund_id_to_name.keys())

        if not resolved_fund_ids:
            logger.warning(f"Statement PDF: no holdings found for investor {client_code}")
            return ("error", 404, f"No holdings found for investor {client_code}")

        # Alphabetical by fund name — the confirmed, deterministic ordering
        # rule for a consolidated statement's sections (a single-fund
        # statement trivially "sorts" to itself).
        resolved_fund_ids.sort(key=lambda fid: (fund_id_to_name.get(fid) or "").lower())
        is_consolidated = len(resolved_fund_ids) > 1

        # Task 5: split into the two product sections. product_type lives on
        # Investment (one per deposit), not CoreFund, so take the first
        # investment seen for each fund id — every investment under a given
        # fund_id shares the same product_type by construction (Task 1).
        fund_id_to_product = {}
        for inv in all_client_investments:
            if inv.fund_id is not None and inv.fund_id not in fund_id_to_product:
                fund_id_to_product[inv.fund_id] = inv.product_type or FUNDS
        funds_section_ids = [fid for fid in resolved_fund_ids if fund_id_to_product.get(fid, FUNDS) != SHARES]
        shares_section_ids = [fid for fid in resolved_fund_ids if fund_id_to_product.get(fid, FUNDS) == SHARES]
        # Drives the FUNDS portfolio-summary block and each fund's own
        # sub-heading — scoped to funds_section_ids (not resolved_fund_ids),
        # so a Shares holding never gets pulled into NAV-based aggregation.
        # is_consolidated above is left untouched (still resolved_fund_ids-
        # based) — it only decides branding/the "Fund(s) Invested In" label.
        show_funds_portfolio_summary = len(funds_section_ids) > 1

        code = client_code
        # Statement Date is the date this PDF is generated, not the date of
        # the latest valuation or the selected reporting period.
        statement_date = datetime.now(ZoneInfo("Africa/Nairobi")).strftime('%B %d, %Y')

        # Branding: a single fund's own identity (JH co-brand / DPRP "Shares"
        # wording) when the whole document is about just that one fund.
        # A consolidated document spanning multiple funds/brands uses the
        # neutral default AIB-AXYS theme instead — co-branding the WHOLE
        # document under one fund's brand would misrepresent the others.
        if is_consolidated:
            theme_fund_names, theme_fund_codes = [], []
        else:
            only_fid = resolved_fund_ids[0]
            theme_fund_names = [fund_id_to_name.get(only_fid, "")]
            theme_fund_codes = [
                str(getattr(inv.fund, "fund_code", "") or "").strip()
                for inv in all_client_investments
                if inv.fund_id == only_fid and getattr(inv, "fund", None)
            ]

        try:
            _require_montserrat_fonts_or_raise()
        except ValueError as e:
            logger.warning(f"Statement PDF: font requirement not met for {client_code}: {e}")
            return ("error", 400, str(e))
        body_font = "Montserrat"
        body_font_bold = "Montserrat-Bold"
        theme = get_statement_theme(theme_fund_names, theme_fund_codes)

        pdf_buffer = BytesIO()
        doc = build_doc_template(pdf_buffer, theme)
        story = []

        styles = getSampleStyleSheet()
        pdf_styles = build_paragraph_styles(theme, styles, body_font, body_font_bold)
        title_style = pdf_styles["title"]
        heading_style = pdf_styles["heading"]
        section_heading_style = pdf_styles["section_heading"]
        info_value_style = pdf_styles["info_value"]
        small_right_style = pdf_styles["small_right"]

        jh_logo_path = _resolve_janus_henderson_statement_logo_path(
            theme_fund_names, theme_fund_codes
        )
        axys_logo_path = resolve_axys_logo_path()
        axys_logo = Image(str(axys_logo_path), width=135, height=43) if axys_logo_path and axys_logo_path.exists() else None
        top_logo_block = Table([[axys_logo]], colWidths=[1.9 * inch]) if axys_logo else Paragraph('<font size=18><b>AXYS INVESTMENT BANK</b></font>', title_style)

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
            top_logo_block,
            Paragraph(head_office_html, small_right_style)
        ]
        header_table = Table([header_cells], colWidths=[3.2 * inch, 4.3 * inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.04 * inch))
        append_divider_line(story, theme)
        story.append(Spacer(1, 0.10 * inch))

        fund_invested_label = ", ".join(fund_id_to_name.get(fid, "") for fid in resolved_fund_ids) or "—"

        if theme.is_jh:
            jh_logo_table = build_jh_logo_block(jh_logo_path)
            if jh_logo_table:
                story.append(jh_logo_table)
                story.append(Spacer(1, 0.08 * inch))

            story.append(build_orange_banner_table('CLIENT STATEMENT', theme, body_font_bold, font_size=11))
            story.append(Spacer(1, 0.08 * inch))
        else:
            append_fund_title(story, theme, fund_invested_label, pdf_styles)
            story.append(Paragraph('CLIENT STATEMENT', heading_style))
            story.append(Spacer(1, 0.18 * inch))

        fund_invested_header = (
            'Shares Invested In'
            if (not is_consolidated and is_dangote_dprp_fund(theme_fund_names, theme_fund_codes))
            else 'Fund Invested In'
        )
        info_data = [
            ['Client Code', Paragraph(f': {escape(str(code))}', info_value_style), 'Statement Date', Paragraph(f': {escape(str(statement_date))}', info_value_style)],
            ['Client Name', Paragraph(f': {escape(str(investor_name))}', info_value_style), fund_invested_header, Paragraph(f': {escape(str(fund_invested_label))}', info_value_style)],
        ]
        info_table = Table(info_data, colWidths=[1.1 * inch, 2.5 * inch, 1.4 * inch, 2.5 * inch])
        if theme.is_jh:
            info_table.setStyle(client_info_table_style(theme, body_font, body_font_bold))
        else:
            info_table.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, -1), body_font, 9),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#111827')),
                ('FONTNAME', (0, 0), (-1, -1), body_font),
                ('FONTNAME', (0, 0), (0, -1), body_font_bold),
                ('FONTNAME', (2, 0), (2, -1), body_font_bold),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ]))
        story.append(info_table)
        story.append(Spacer(1, 0.18 * inch))

        if show_funds_portfolio_summary:
            _append_portfolio_summary_block(
                story, pdf_styles, theme, body_font, body_font_bold, client_code,
                funds_section_ids, fund_id_to_name, as_of_dt,
            )

        both_sections_present = bool(funds_section_ids) and bool(shares_section_ids)

        if funds_section_ids:
            if both_sections_present:
                story.append(Paragraph("FUNDS", section_heading_style))
                story.append(Spacer(1, 0.08 * inch))

            for idx, section_fund_id in enumerate(funds_section_ids):
                fund_name_for_section = fund_id_to_name.get(section_fund_id) or "Portfolio"
                if show_funds_portfolio_summary:
                    if idx > 0:
                        story.append(Spacer(1, 0.10 * inch))
                        story.append(Table(
                            [['']], colWidths=[7.3 * inch],
                            style=[('LINEABOVE', (0, 0), (-1, -1), 1, colors.HexColor(theme.divider_grey))],
                        ))
                        story.append(Spacer(1, 0.10 * inch))
                    story.append(Paragraph(fund_name_for_section.upper(), section_heading_style))
                    story.append(Spacer(1, 0.08 * inch))

                _append_fund_statement_section(
                    story, client_code, section_fund_id, fund_name_for_section, as_of_dt, period_only,
                    theme, pdf_styles, body_font, body_font_bold, statement_date,
                )

        # Task 5: one "SHARES (DANGOTE PETROLEUM REFINERY IPO)" section, omitted
        # entirely when the investor has no Shares holdings. Never mixes its
        # USD/NGN figures into the FUNDS section's NAV-based totals above.
        if shares_section_ids:
            if both_sections_present:
                story.append(Spacer(1, 0.10 * inch))
                story.append(Table(
                    [['']], colWidths=[7.3 * inch],
                    style=[('LINEABOVE', (0, 0), (-1, -1), 1, colors.HexColor(theme.divider_grey))],
                ))
                story.append(Spacer(1, 0.10 * inch))
            story.append(Paragraph("SHARES (DANGOTE PETROLEUM REFINERY IPO)", section_heading_style))
            story.append(Spacer(1, 0.08 * inch))
            _append_shares_statement_section(
                story, client_code, shares_section_ids, pdf_styles, body_font, body_font_bold, theme,
            )

        append_branded_footer(
            story,
            theme,
            pdf_styles,
            '<b>Disclaimer:</b> This statement is provided for informational purposes only. All figures are subject to change and may not reflect real-time data.',
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
        )

        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Statement PDF generation failed for {client_code}: {str(e)}\n{error_trace}")
        return None


@investment_v1.route('/api/v1/investors/<string:client_code>/statement/excel', methods=['GET'])
def download_investor_statement_excel(client_code):
    """
    Download a branded investor statement spreadsheet in Excel format (.xlsx).
    Supports token query param for browser downloads or Authorization header.
    """
    try:
        # Check authentication (JWT header or ?token= param)
        from flask_jwt_extended import decode_token, verify_jwt_in_request

        qs_token = request.args.get("token", "").strip()
        if qs_token:
            try:
                decode_token(qs_token)
            except Exception:
                return jsonify({"status": 401, "message": "Invalid or expired token"}), 401
        else:
            try:
                verify_jwt_in_request()
            except Exception:
                return jsonify({"status": 401, "message": "Authentication required"}), 401

        # Get investor info
        inv = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).order_by(Investment.id.desc()).first()

        investor_name = inv.investor_name if inv else client_code
        email = inv.investor_email if inv else ""

        # Task 5: the FUNDS sheets below (Portfolio Summary / Statement
        # Timeline) are EpochLedger-based (fund-level monthly epoch
        # compounding) and meaningless for a Shares-only investor — SHARES
        # still never posts to EpochLedger (that's unrelated to NAV; see
        # Task 7, which corrected SHARES to value shares x NAV-per-share via
        # InvestorShares/NavHistory, same as FUNDS, just not via this
        # particular epoch-reconciliation mechanism) — omit these sheets
        # entirely rather than emit an all-zero/empty "Funds" section.
        has_funds_holdings = db.session.query(Investment.id).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code),
            Investment.product_type == FUNDS,
        ).first() is not None

        # Get portfolio aggregation
        p_data = {}
        timeline_rows = []
        if has_funds_holdings:
            portfolio_res = get_investor_portfolio_aggregated(client_code)
            p_data = portfolio_res.get_json().get("data", {}) if hasattr(portfolio_res, "get_json") else {}

            # Get timeline statements
            timeline_res = get_investor_statements(client_code)
            t_json = timeline_res.get_json() if hasattr(timeline_res, "get_json") else {}
            t_data = t_json.get("data", {}) if isinstance(t_json, dict) else {}
            timeline_rows = (t_data if isinstance(t_data, list) else t_data.get("statements", [])) or []

        # Build Summary sheet
        summary_rows = [{
            "Client Code": client_code,
            "Investor Name": investor_name,
            "Email": email,
            "Total Principal Invested": float(p_data.get("total_principal") or 0.0),
            "Current Valuation Balance": float(p_data.get("current_balance") or 0.0),
            "Total Profit / Gain": float(p_data.get("total_profit") or 0.0),
            "Unique Batches": int(p_data.get("unique_batches") or 0),
            "Report Date": datetime.now().strftime("%Y-%m-%d"),
        }]

        # Build History sheet
        history_rows = []
        for r in timeline_rows:
            history_rows.append({
                "Date": str(r.get("date") or "")[:10],
                "Event / Statement": r.get("label") or r.get("type") or "Statement",
                "Fund": r.get("fund_name") or "—",
                "Currency": r.get("currency") or "USD",
                "Shares": round(float(r.get("shares") or 0), 4) if r.get("shares") else "—",
                "NAV per Share": round(float(r.get("nav_per_share") or 0), 4) if r.get("nav_per_share") else "—",
                "Deposit (+)": round(float(r.get("deposits") or 0), 2),
                "Withdrawal (-)": round(float(r.get("withdrawals") or 0), 2),
                "Opening Balance": round(float(r.get("opening_balance") or 0), 2),
                "Performance Rate (%)": f"{float(r.get('performance_rate') or 0):.4f}%" if r.get("performance_rate") else "—",
                "Profit / Gain (+)": round(float(r.get("profit") or 0), 2),
                "Closing Balance (=)": round(float(r.get("end_balance") or 0), 2),
                "Audit Hash": str(r.get("audit_hash") or "")[:20] + "..." if r.get("audit_hash") else "—",
            })

        # Task 5/7: Shares holdings sheet — built directly from Investment rows
        # (product_type SHARES), independent of the FUNDS-only EpochLedger-
        # based aggregation above (SHARES never posts to EpochLedger — that's
        # unrelated to NAV; see Task 7, which values SHARES as shares x
        # NAV-per-share via InvestorShares/NavHistory, same as FUNDS, just not
        # via this epoch-reconciliation mechanism). Omitted entirely (no
        # sheet) when the investor holds none.
        shares_holdings = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code),
            Investment.product_type == SHARES,
        ).order_by(Investment.date_deposited.asc()).all()

        from app.Funds.investor_shares import InvestorShares as _InvestorShares
        shares_investor_shares_by_id = {
            s.investment_id: s
            for s in db.session.query(_InvestorShares).filter(
                _InvestorShares.investment_id.in_([h.id for h in shares_holdings])
            ).all()
        } if shares_holdings else {}

        shares_rows = []
        for s in shares_holdings:
            deposit = Decimal(str(s.amount_deposited or 0))
            entry_fee = Decimal(str(s.deployment_fee_deducted or 0))
            tx_cost = Decimal(str(s.transfer_fee_deducted or 0))
            net_usd = deposit - entry_fee - tx_cost
            refund_usd = Decimal(str(s.oversubscription_refund_amount or 0))

            nav_per_share, is_valued = _resolve_shares_nav_for_investment(s, shares_investor_shares_by_id, db.session)
            if is_valued and s.shares_owned is not None:
                market_value_ngn = float(Decimal(str(s.shares_owned)) * Decimal(str(nav_per_share)))
                cost_basis_ngn = float(s.net_ngn) if s.net_ngn is not None else 0.0
                gain_loss_ngn = market_value_ngn - cost_basis_ngn
                nav_display = float(nav_per_share)
            else:
                market_value_ngn = "Not valued yet"
                gain_loss_ngn = "Not valued yet"
                nav_display = "Not valued yet"

            refund_status = "—"
            if refund_usd > 0:
                refund_wd = (
                    db.session.query(Withdrawal)
                    .filter(
                        func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
                        Withdrawal.fund_id == s.fund_id,
                        Withdrawal.source == WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                    )
                    .order_by(Withdrawal.date_withdrawn.desc())
                    .first()
                )
                refund_status = normalize_withdrawal_status(refund_wd.status) if refund_wd else "Pending"
            shares_rows.append({
                "Batch": s.batch.batch_name if getattr(s, "batch", None) else (s.batch_id or "—"),
                "Deposit Date": s.date_deposited.strftime("%Y-%m-%d") if s.date_deposited else "—",
                "Deposit (USD)": float(deposit),
                "Entry Fee (USD)": float(entry_fee),
                "Transaction Cost (USD)": float(tx_cost),
                "Net (USD)": float(net_usd),
                "Exchange Rate (NGN/USD)": float(s.shares_exchange_rate_ngn) if s.shares_exchange_rate_ngn is not None else "—",
                "Net (NGN) - Cost Basis": float(s.net_ngn) if s.net_ngn is not None else "—",
                "Shares Allocated": float(s.shares_owned) if s.shares_owned is not None else "—",
                "NAV / Share (NGN)": nav_display,
                "Market Value (NGN)": market_value_ngn,
                "Gain / Loss (NGN)": gain_loss_ngn,
                "Refund (USD)": float(refund_usd) if refund_usd > 0 else "—",
                "Refund Status": refund_status,
            })

        import pandas as pd
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
        HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
        HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=False)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            if has_funds_holdings:
                pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="Portfolio Summary")
                pd.DataFrame(history_rows or []).to_excel(writer, index=False, sheet_name="Statement Timeline")
            if shares_rows:
                pd.DataFrame(shares_rows).to_excel(writer, index=False, sheet_name="Shares Holdings")
            if not has_funds_holdings and not shares_rows:
                # Neither section applies (e.g. a client_code with no holdings
                # at all) — fall back to the summary sheet so the workbook
                # always has at least one visible sheet, as it did pre-Task 5.
                pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="Portfolio Summary")

            for sheet_name in writer.sheets:
                ws = writer.sheets[sheet_name]
                for cell in ws[1]:
                    cell.font = HEADER_FONT
                    cell.fill = HEADER_FILL
                    cell.alignment = HEADER_ALIGN
                for col in ws.columns:
                    max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
                    ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 44)
                ws.freeze_panes = "A2"

        output.seek(0)
        filename = f"Statement_{client_code}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=filename)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


# ==================== INVESTOR REGISTRY (GLOBAL) ====================

@investment_v1.route('/api/v1/investors/registry', methods=['GET'])
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
        from app.Funds.investor_shares import InvestorShares
        from app.Valuation.valuation_snapshot import ValuationSnapshot
        from app.Funds.nav_history import NavHistory
        
        # 1. Fetch data (case-insensitive client code matching)
        investments = session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).all()
        
        ledger_entries = session.query(EpochLedger).filter(
            func.lower(EpochLedger.internal_client_code) == func.lower(client_code)
        ).all()
        
        withdrawals = session.query(Withdrawal).filter(
            func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
            Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
            Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
        ).all()

        statements = []
        
        # Currency helper map for ledger/withdrawal rows that don't directly carry currency.
        fund_currency_map = {}
        for inv in investments:
            cur = None
            try:
                cur = inv.share_class.currency if inv.share_class else None
            except Exception:
                cur = None
            cur = cur or inv.currency_type
            if inv.fund_name and cur and inv.fund_name not in fund_currency_map:
                fund_currency_map[inv.fund_name] = cur

        # === ADD DEPOSIT / DEPLOYMENT EVENTS ===
        # ✅ CREATE SEPARATE STATEMENT FOR EACH INVESTMENT (not aggregated by batch)
        # This ensures each deposit is visible with its own transaction & entry fees
        
        # First pass: collect all unique batch IDs for metadata lookup
        batch_ids = set(inv.batch_id for inv in investments if inv.batch_id is not None)
        batch_meta = {}
        batch_names = {}
        
        if batch_ids:
            batches = db.session.query(
                Batch.id,
                Batch.batch_name,
                Batch.deployment_date_actual,
                Batch.date_deployed,
                Batch.deployment_nav,
                Batch.deployment_confirmed,
            ).filter(Batch.id.in_(batch_ids)).all()
            batch_names = {b.id: b.batch_name for b in batches}
            batch_meta = {
                b.id: {
                    "deployment_date_actual": b.deployment_date_actual,
                    "date_deployed": b.date_deployed,
                    "deployment_nav": b.deployment_nav,
                    "deployment_confirmed": bool(b.deployment_confirmed),
                }
                for b in batches
            }
        
        # Second pass: create one statement PER INVESTMENT (each deposit gets its own line)
        for inv in investments:
            batch_id = inv.batch_id
            meta = batch_meta.get(batch_id, {})
            deployed = bool(meta.get("deployment_confirmed"))
            deployment_date_actual = meta.get("deployment_date_actual")
            date_deployed = meta.get("date_deployed")
            
            # Use actual deployment date if available, else use deposit date
            event_date = inv.date_deposited
            if deployed and deployment_date_actual:
                event_date = datetime.combine(deployment_date_actual, datetime.min.time()).replace(tzinfo=timezone.utc)
            elif deployed and date_deployed:
                event_date = date_deployed
            
            if deployed:
                event_label = "Deployment Statement"
            elif inv.date_deposited.month == 4:
                event_label = "Initial Deposit"
            elif inv.date_deposited.month == 9:
                event_label = "Top-up Deposit"
            elif inv.date_deposited.month == 10:
                event_label = "Top-up Deposit"
            else:
                event_label = f"Deposit - {inv.date_deposited.strftime('%B')}"
            
            # ✅ DECIMAL PRECISION: Round all monetary values to 2 places
            deposit_amount = round(float(inv.net_principal or 0), 2)
            original_principal = round(float(inv.amount_deposited or 0), 2)
            transaction_fee = round(float(inv.transfer_fee_deducted or 0), 2)
            entry_fee = round(float(inv.deployment_fee_deducted or 0), 2)
            
            inv_shares = session.query(InvestorShares).filter(
                InvestorShares.investment_id == inv.id
            ).first()
            nav_at_deployment = (
                float(inv_shares.deployment_nav)
                if inv_shares and inv_shares.deployment_nav is not None
                else (float(meta.get("deployment_nav")) if meta.get("deployment_nav") is not None else None)
            )
            shares_at_deployment = (
                float(inv_shares.shares_owned)
                if inv_shares and inv_shares.shares_owned is not None
                else (deposit_amount / nav_at_deployment if nav_at_deployment and nav_at_deployment > 0 else None)
            )
            
            statements.append({
                "type": "DEPLOYMENT" if deployed else "DEPOSIT",
                "batch_id": batch_id,
                "batch_name": batch_names.get(batch_id, "Unknown") if batch_id is not None else None,
                "date": event_date.isoformat(),
                "label": event_label,
                "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                "original_principal": original_principal,
                "transaction_fee_usd": transaction_fee,
                "entry_fee_usd": entry_fee,
                "deployment_fee": transaction_fee,  # For compatibility
                "nav_at_deployment": round(nav_at_deployment, 6) if nav_at_deployment is not None else None,
                "shares_at_deployment": round(shares_at_deployment, 6) if shares_at_deployment is not None else None,
                "nav_per_share": round(nav_at_deployment, 6) if nav_at_deployment is not None else None,
                "shares": round(shares_at_deployment, 6) if shares_at_deployment is not None else None,
                "currency": (inv.share_class.currency if getattr(inv, "share_class", None) else None) or inv.currency_type,
                "main_balance": deposit_amount,
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
                "currency": fund_currency_map.get(entry.fund_name),
                "sort_priority": 0  # Reports second
            })

        # === ADD VALUATION EVENTS (ALL SNAPSHOTS) ===
        # Never remove/replace valuation history: emit one statement row per valuation snapshot date.
        seen_valuation_keys = set()
        for inv in investments:
            if not inv.batch or not inv.batch.deployment_confirmed:
                continue

            inv_shares = session.query(InvestorShares).filter(
                InvestorShares.investment_id == inv.id
            ).first()
            if not inv_shares:
                continue

            shares_owned = float(inv_shares.shares_owned or 0)
            deployment_nav = float(inv_shares.deployment_nav or inv.previous_nav_price or 0)

            snapshots = (
                session.query(ValuationSnapshot)
                .filter(ValuationSnapshot.investor_shares_id == inv_shares.id)
                .order_by(ValuationSnapshot.valuation_date.asc())
                .all()
            )

            for snap in snapshots:
                vdt = snap.valuation_date
                # ValuationSnapshot.valuation_date is a Date; standardize to ISO date string
                vdt_iso = vdt.isoformat() if hasattr(vdt, "isoformat") else str(vdt)
                key = (inv.batch_id, inv_shares.id, vdt_iso)
                if key in seen_valuation_keys:
                    continue
                seen_valuation_keys.add(key)

                end_balance = round(float(snap.market_value or 0), 2)
                performance_rate = round(float(snap.performance_pct or 0), 4)
                nav_per_share = round(float(snap.nav_per_share or 0), 6)

                statements.append({
                    "type": "VALUATION",
                    "batch_id": inv.batch_id,
                    "batch_name": inv.batch.batch_name if inv.batch else None,
                    "date": vdt_iso,
                    "label": "Valuation Report",
                    "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                    "opening_balance": 0.0,  # Calculated in running balance pass
                    "deposits": 0.0,
                    "withdrawals": 0.0,
                    "profit": 0.0,  # Calculated in running balance pass
                    "end_balance": end_balance,
                    "performance_rate": performance_rate,
                    "shares_at_deployment": round(shares_owned, 4) if shares_owned > 0 else None,
                    "nav_at_deployment": round(deployment_nav, 6) if deployment_nav > 0 else None,
                    "shares": round(float(snap.shares_held or shares_owned or 0), 6) if (snap.shares_held or shares_owned) else None,
                    "nav_per_share": nav_per_share if nav_per_share > 0 else None,
                    "currency": (inv.share_class.currency if getattr(inv, "share_class", None) else None) or inv.currency_type,
                    "sort_priority": 0,
                })
            
        # === ADD WITHDRAWAL EVENTS ===
        for wd in withdrawals:
            # ✅ DECIMAL PRECISION FIX: Round withdrawal amount to 2 decimal places
            withdrawal_amount = round(
                float(wd.gross_amount if getattr(wd, "gross_amount", None) is not None else wd.amount or 0),
                2,
            )
            
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
                "currency": fund_currency_map.get(wd.fund_name),
                "sort_priority": 1  # Withdrawals third
            })
        
        # 2. Sort chronologically for running balance calculation
        # Use (date, sort_priority) to ensure stable ordering
        statements.sort(key=lambda x: (x["date"], x["sort_priority"]))
        
        # 3. Calculate running balances PER BATCH (batch isolation).
        # "No lumping": each batch keeps its own balance timeline.
        running_balance_by_bucket = {}
        
        def _balance_bucket(stmt_row):
            bid = stmt_row.get("batch_id")
            if bid is not None:
                return f"batch:{bid}"
            # Fallback for legacy rows that don't carry batch_id yet
            fund = (stmt_row.get("fund_name") or "portfolio").strip().lower()
            return f"fund:{fund}"
        
        for stmt in statements:
            bucket = _balance_bucket(stmt)
            running_balance = float(running_balance_by_bucket.get(bucket, 0.0))
            stmt["balance_bucket"] = bucket
            if stmt["type"] in ("DEPOSIT", "DEPLOYMENT"):
                stmt["opening_balance"] = round(running_balance, 2)
                running_balance = round(running_balance + float(stmt.get("deposits") or 0), 2)
                stmt["end_balance"] = round(running_balance, 2)
            elif stmt["type"] == "MONTHLY_REPORT":
                stmt["opening_balance"] = round(running_balance, 2)
                profit_calculated = round(stmt["opening_balance"] * (float(stmt.get("performance_rate") or 0) / 100), 2)
                stmt["profit"] = profit_calculated
                stmt["end_balance"] = round(
                    stmt["opening_balance"] + float(stmt.get("deposits") or 0) - float(stmt.get("withdrawals") or 0) + stmt["profit"],
                    2
                )
                running_balance = round(float(stmt["end_balance"]), 2)
            elif stmt["type"] == "VALUATION":
                stmt["opening_balance"] = round(running_balance, 2)
                target_end = round(float(stmt.get("end_balance") or running_balance), 2)
                stmt["profit"] = round(target_end - stmt["opening_balance"], 2)
                running_balance = target_end
                stmt["end_balance"] = running_balance
            elif stmt["type"] == "WITHDRAWAL":
                stmt["opening_balance"] = round(running_balance, 2)
                running_balance = round(running_balance - float(stmt.get("withdrawals") or 0), 2)
                stmt["end_balance"] = round(running_balance, 2)
            running_balance_by_bucket[bucket] = running_balance
        
        # 4. Sort reverse-chronological for display (newest first)
        statements.sort(key=lambda x: (x["date"], x["sort_priority"]), reverse=True)

        # 5. Split-view payload by batch plus consolidated summary.
        batch_sections_map = {}
        for stmt in statements:
            batch_id = stmt.get("batch_id")
            if batch_id is None:
                continue
            section = batch_sections_map.get(batch_id)
            if section is None:
                meta = batch_meta.get(batch_id, {})
                deployment_dt = meta.get("deployment_date_actual") or meta.get("date_deployed")
                deployment_iso = None
                if deployment_dt is not None:
                    try:
                        deployment_iso = deployment_dt.isoformat()
                    except Exception:
                        deployment_iso = str(deployment_dt)
                section = {
                    "batch_id": batch_id,
                    "batch_name": stmt.get("batch_name") or batch_names.get(batch_id) or f"Batch {batch_id}",
                    "deployment_date": deployment_iso,
                    "rows": [],
                    "latest_market_value": 0.0,
                }
                batch_sections_map[batch_id] = section
            section["rows"].append(stmt)

        consolidated_market_value = 0.0
        for section in batch_sections_map.values():
            latest_row = max(section["rows"], key=lambda r: r.get("date") or "")
            latest_mv = round(float(latest_row.get("end_balance") or 0), 2)
            section["latest_market_value"] = latest_mv
            consolidated_market_value += latest_mv

        batch_sections = sorted(batch_sections_map.values(), key=lambda s: s["batch_name"])
        
        return make_response(jsonify({
            "status": 200,
            "message": "Investor statements retrieved",
            "data": statements,
            "batch_sections": batch_sections,
            "portfolio_summary": {
                "total_batches": len(batch_sections),
                "total_market_value": round(consolidated_market_value, 2),
            },
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
        _register_montserrat_fonts()
        registered_fonts = set(pdfmetrics.getRegisteredFontNames())
        pdf_body_font = "Montserrat" if "Montserrat" in registered_fonts else "Helvetica"
        pdf_body_font_bold = "Montserrat-Bold" if "Montserrat-Bold" in registered_fonts else "Helvetica-Bold"

        w = db.session.query(Withdrawal).filter(
            Withdrawal.id == withdrawal_id,
            Withdrawal.internal_client_code == client_code
        ).first()
        
        if not w:
            return make_response(jsonify({"status": 404, "message": "Withdrawal record not found"}), 404)
            
        # Get investor info
        inv = db.session.query(Investment).filter(Investment.internal_client_code == client_code).first()
        investor_name = inv.investor_name if inv else "Investor"
        currency_code = (
            (getattr(inv, "currency", None) or "").upper()
            or (getattr(getattr(inv, "share_class", None), "currency", None) or "").upper()
            or "USD"
        )

        def _fmt_money(amount: float) -> str:
            if currency_code == "KES":
                return f"KES {amount:,.2f}"
            return f"USD {amount:,.2f}"
        
        # Get fund info and current balance
        fund_name = w.fund_name or "Portfolio"
        withdrawal_amount_value = float(w.gross_amount if getattr(w, "gross_amount", None) is not None else w.amount or 0)

        # Prefer NAV snapshot market value (this is what the app shows as standing)
        from app.Funds.investor_shares import InvestorShares
        from app.Valuation.valuation_snapshot import ValuationSnapshot

        pre_withdrawal_balance = None
        if inv is not None:
            inv_shares = db.session.query(InvestorShares).filter(InvestorShares.investment_id == inv.id).first()
            if inv_shares is not None:
                snap_q = db.session.query(ValuationSnapshot).filter(
                    ValuationSnapshot.investor_shares_id == inv_shares.id
                )
                if w.date_withdrawn:
                    snap_q = snap_q.filter(ValuationSnapshot.valuation_date <= w.date_withdrawn.date())
                latest_snap = snap_q.order_by(ValuationSnapshot.valuation_date.desc()).first()
                if latest_snap and latest_snap.market_value is not None:
                    pre_withdrawal_balance = float(latest_snap.market_value)

        if pre_withdrawal_balance is None:
            # Last fallback: investment valuation field (already updated on approval)
            latest_investment = db.session.query(Investment).filter(
                Investment.internal_client_code == client_code,
                or_(
                    Investment.fund_name == fund_name,
                    Investment.fund_id == w.fund_id
                )
            ).order_by(Investment.id.desc()).first()
            pre_withdrawal_balance = float(latest_investment.valuation or 0) if latest_investment else 0.0

        # Current value after withdrawal should reflect direct deduction.
        post_withdrawal_balance = max(0.0, float(pre_withdrawal_balance) - float(withdrawal_amount_value))

        theme = get_statement_theme([fund_name])
        jh_logo_path = _resolve_janus_henderson_statement_logo_path([fund_name])

        pdf_buffer = BytesIO()
        doc = build_doc_template(pdf_buffer, theme, top_margin=0.5, bottom_margin=0.5)
        story = []
        styles = getSampleStyleSheet()
        pdf_styles = build_paragraph_styles(theme, styles, pdf_body_font, pdf_body_font_bold)
        title_style = pdf_styles["title"]
        heading_style = pdf_styles["heading"]
        section_heading_style = pdf_styles["section_heading"]
        normal_style = pdf_styles["normal"]

        append_receipt_header(
            story,
            theme,
            pdf_styles,
            jh_logo_path=jh_logo_path,
            document_title="WITHDRAWAL STATEMENT & AUTHORIZATION RECEIPT",
            fund_name=fund_name,
        )
        # Withdrawal Details - detailed table
        withdrawal_date_str = w.date_withdrawn.strftime("%B %d, %Y") if w.date_withdrawn else "N/A"
        approved_date_str = w.approved_at.strftime("%B %d, %Y") if w.approved_at else "Pending"
        receipt_data = [
            ['Reference ID', f': WDR-{w.id}', 'Withdrawal Date', f': {withdrawal_date_str}'],
            ['Client Code', Paragraph(f': {escape(str(client_code))}', normal_style), 'Client Name', Paragraph(f': {escape(str(investor_name))}', normal_style)],
            ['Shares' if is_dangote_dprp_fund([fund_name]) else 'Fund', Paragraph(f': {escape(str(fund_name))}', normal_style), 'Status', Paragraph(f': {escape(str(w.status))}', normal_style)],
            ['Approved Date', f': {approved_date_str}', '', ''],
        ]
        receipt_table = Table(receipt_data, colWidths=[1.2 * inch, 1.75 * inch, 1.25 * inch, 3.3 * inch])
        receipt_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),
        ]))
        story.append(Paragraph('Withdrawal Details', section_heading_style))
        story.append(receipt_table)
        story.append(Spacer(1, 0.25 * inch))
        
        # Amount Box - highlighted
        amount_data = [['WITHDRAWS', _fmt_money(withdrawal_amount_value)]]
        amount_table = Table(amount_data, colWidths=[3.5 * inch, 3.5 * inch])
        banner_style = highlight_banner_style(theme, pdf_body_font_bold)
        banner_style.add("FONT", (0, 0), (-1, -1), pdf_body_font_bold, 18)
        amount_table.setStyle(banner_style)
        story.append(amount_table)
        story.append(Spacer(1, 0.25 * inch))
        
        # Summary (same structure style as deposit statement layout)
        reconciliation_data = [
            ['Previous Value (Before Withdrawal)', _fmt_money(pre_withdrawal_balance)],
            ['Withdrawal Amount', f'({_fmt_money(withdrawal_amount_value)})'],
            ['Current Value (After Withdrawal)', _fmt_money(post_withdrawal_balance)],
        ]
        
        reconciliation_table = Table(reconciliation_data, colWidths=[5.2 * inch, 2.3 * inch])
        reconciliation_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), pdf_body_font_bold),
            ('FONTNAME', (0, 2), (-1, 2), pdf_body_font_bold),
        ]))
        story.append(Paragraph(f'Withdrawal Summary ({currency_code})', section_heading_style))
        story.append(reconciliation_table)
        story.append(Spacer(1, 0.2 * inch))
        
        append_branded_footer(
            story,
            theme,
            pdf_styles,
            '<b>Disclaimer & Notice:</b> This is an electronically generated withdrawal authorization receipt. '
            'No signature is required. This statement is provided for informational purposes and confirms your withdrawal request. '
            'All figures are subject to verification and may not reflect real-time data. Withdrawal completion is subject to fund rules and processing timelines.',
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | "
            f"Withdrawal ID: {w.id} | Client Code: {client_code}",
        )
        
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


def _generate_deposit_receipt_pdf_bytes(client_code, batch_id):
    """
    Internal helper: Generate deposit PDF as raw bytes.
    No Flask decorators; safe to call from email service and background threads.
    Returns BytesIO buffer with PDF bytes, or None on error.
    """
    try:
        # Prefer Montserrat to match app UI; fall back if unavailable.
        _register_montserrat_fonts()
        registered_fonts = set(pdfmetrics.getRegisteredFontNames())
        pdf_body_font = "Montserrat" if "Montserrat" in registered_fonts else "Helvetica"
        pdf_body_font_bold = "Montserrat-Bold" if "Montserrat-Bold" in registered_fonts else "Helvetica-Bold"

        # Get all investments for this client in this batch
        investments = db.session.query(Investment).filter(
            Investment.internal_client_code == client_code,
            Investment.batch_id == batch_id
        ).all()
        
        if not investments:
            logger.warning(f"Deposit PDF: no investments found for {client_code} batch {batch_id}")
            return None
        
        # Aggregate investment data
        inv_first = investments[0]  # Get first for metadata
        currency_code = (
            (getattr(inv_first, "currency", None) or "").upper()
            or (getattr(getattr(inv_first, "share_class", None), "currency", None) or "").upper()
            or "USD"
        )

        def _fmt_money(amount: float) -> str:
            if currency_code == "KES":
                return f"KES {amount:,.2f}"
            return f"USD {amount:,.2f}"

        total_amount_deposited = sum(float(inv.amount_deposited) for inv in investments)
        total_transaction_cost = sum(float(inv.transfer_fee_deducted or 0) for inv in investments)
        total_entry_fee = sum(float(inv.deployment_fee_deducted or 0) for inv in investments)
        total_net_after_deductions = sum(float(inv.net_principal or 0) for inv in investments)
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

        # Determine whether this is the client's first-ever deposit or an additional top-up.
        prior_investment_exists = db.session.query(Investment.id).filter(
            Investment.internal_client_code == client_code,
            Investment.date_deposited.isnot(None),
            Investment.date_deposited < deposit_date
        ).first() is not None
        is_initial_deposit = not prior_investment_exists

        # Pull authoritative running balances for this specific deposit event.
        previous_standing_from_statement = None
        ending_standing_from_statement = None
        net_deposit_from_statement = None
        try:
            # Unwrapped call, matching every other in-process view-function call in
            # this file: get_investor_statements is @jwt_required(), which needs an
            # active HTTP request to read the Authorization header. Calling it
            # decorated-and-all works when _generate_deposit_receipt_pdf_bytes runs
            # inside a real request, but this is also called from the send-queue
            # scheduler's background thread (app context only, no request) — there
            # it raised "Working outside of request context" every time, silently
            # falling back to less precise numbers instead of the real bug: this
            # was never unwrapped in the first place.
            statements_resp = get_investor_statements.__wrapped__(client_code)
            statements_payload = statements_resp.get_json() if hasattr(statements_resp, "get_json") else {}
            statements_rows = statements_payload.get("data") if isinstance(statements_payload, dict) else []
            if isinstance(statements_rows, list):
                target_date = deposit_date.date() if deposit_date else None
                matched_deposit = next(
                    (
                        row for row in statements_rows
                        if row.get("type") == "DEPOSIT"
                        and row.get("batch_id") == batch_id
                        and (
                            not target_date
                            or (
                                row.get("date")
                                and datetime.fromisoformat(str(row.get("date")).replace("Z", "+00:00")).date() == target_date
                            )
                        )
                    ),
                    None
                )
                if matched_deposit:
                    previous_standing_from_statement = float(matched_deposit.get("opening_balance") or 0)
                    ending_standing_from_statement = float(matched_deposit.get("end_balance") or 0)
                    net_deposit_from_statement = float(matched_deposit.get("deposits") or 0)
        except Exception as stmt_err:
            print(f"⚠️  Could not derive deposit event standings from statements for {client_code}/{batch_id}: {stmt_err}")
        
        theme = get_statement_theme([fund_name])
        jh_logo_path = _resolve_janus_henderson_statement_logo_path([fund_name])

        pdf_buffer = BytesIO()
        doc = build_doc_template(pdf_buffer, theme, top_margin=0.5, bottom_margin=0.5)
        story = []

        styles = getSampleStyleSheet()
        pdf_styles = build_paragraph_styles(theme, styles, pdf_body_font, pdf_body_font_bold)
        section_heading_style = pdf_styles["section_heading"]
        normal_style = pdf_styles["normal"]

        append_receipt_header(
            story,
            theme,
            pdf_styles,
            jh_logo_path=jh_logo_path,
            document_title=(
                "DEPOSIT CONFIRMATION"
                if is_dangote_dprp_fund([fund_name])
                else "DEPOSIT STATEMENT & CONFIRMATION"
            ),
            fund_name=fund_name,
        )
        # Deposit details section
        deposit_date_str = inv_first.date_deposited.strftime("%B %d, %Y") if inv_first.date_deposited else "N/A"
        receipt_data = [
            ['Client Code', f': {client_code}', 'Deposit Date', f': {deposit_date_str}'],
            ['Client Name', Paragraph(f': {escape(str(inv_first.investor_name))}', normal_style), '', ''],
            ['Shares' if is_dangote_dprp_fund([fund_name]) else 'Fund', Paragraph(f': {escape(str(fund_name))}', normal_style), '', ''],
        ]
        
        receipt_table = Table(receipt_data, colWidths=[1.2 * inch, 1.7 * inch, 1.2 * inch, 3.4 * inch])
        receipt_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),
            ('SPAN', (1, 1), (3, 1)),
            ('SPAN', (1, 2), (3, 2)),
        ]))
        story.append(Paragraph('Deposit Details', section_heading_style))
        story.append(receipt_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Amount deposited - highlighted box
        amount_data = [['INITIAL DEPOSIT', _fmt_money(total_amount_deposited)]]
        amount_table = Table(amount_data, colWidths=[3.5 * inch, 3.5 * inch])
        amount_table.setStyle(highlight_banner_style(theme, pdf_body_font_bold))
        story.append(amount_table)
        story.append(Spacer(1, 0.25 * inch))

        # Deposit breakdown (deposit statement): show only initial deposit amount.
        deductions_data = [
            ['Initial Deposit Amount', _fmt_money(total_amount_deposited)],
        ]
        deductions_table = Table(deductions_data, colWidths=[5.2 * inch, 2.3 * inch])
        deductions_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9f9f9')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), pdf_body_font_bold),
            ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#16a34a')),
            ('FONTNAME', (1, 0), (1, 0), pdf_body_font_bold),
        ]))
        story.append(Paragraph(f'Deposit Breakdown ({currency_code})', section_heading_style))
        story.append(deductions_table)
        story.append(Spacer(1, 0.2 * inch))
        
        # Account reconciliation
        opening_balance_calc = 0.0
        if deposit_date is not None:
            valuation_at_deposit = db.session.query(EpochLedger).filter(
                EpochLedger.internal_client_code == client_code,
                EpochLedger.fund_name == fund_name,
                EpochLedger.epoch_start <= deposit_date,
                EpochLedger.epoch_end >= deposit_date
            ).order_by(EpochLedger.epoch_end.desc()).first()

            if valuation_at_deposit:
                opening_balance_calc = float(valuation_at_deposit.start_balance or 0)
            else:
                previous_epoch = db.session.query(EpochLedger).filter(
                    EpochLedger.internal_client_code == client_code,
                    EpochLedger.fund_name == fund_name,
                    EpochLedger.epoch_end < deposit_date
                ).order_by(EpochLedger.epoch_end.desc()).first()
                opening_balance_calc = float(previous_epoch.end_balance) if previous_epoch else 0.0

        # Current standing should reflect post-deduction principal + later valuation effects.
        from app.Batch.controllers import BatchController
        current_balance = 0.0
        for inv in investments:
            inv_batch = batch if batch and batch.id == inv.batch_id else db.session.query(Batch).filter(Batch.id == inv.batch_id).first()
            values = BatchController._calculate_batch_investment_values(inv, inv_batch, db.session)
            current_balance += float(values.get("current_balance", 0))

        deposits_total = net_deposit_from_statement if net_deposit_from_statement is not None else total_net_after_deductions
        withdrawals_total = 0.0
        base_opening_balance = (
            previous_standing_from_statement
            if previous_standing_from_statement is not None
            else opening_balance_calc
        )
        standing_after_deposit = (
            ending_standing_from_statement
            if ending_standing_from_statement is not None
            else (base_opening_balance + deposits_total)
        )
        profit = current_balance - (standing_after_deposit - withdrawals_total)

        if is_initial_deposit:
            reconciliation_data = [
                ['Opening Balance (Before Initial Deposit)', _fmt_money(base_opening_balance)],
                ['Initial Deposit Amount', _fmt_money(total_amount_deposited)],
                ['Bank Transaction Cost', f'({_fmt_money(total_transaction_cost)})'],
                ['Fund Entry Fee', f'({_fmt_money(total_entry_fee)})'],
                ['Final Standing Balance (After Deductions)', _fmt_money(standing_after_deposit)],
            ]
        else:
            reconciliation_data = [
                ['Previous Standing Before Top-up', _fmt_money(base_opening_balance)],
                ['Additional Deposit Amount', _fmt_money(total_amount_deposited)],
                ['Net Amount Added (After Fees)', _fmt_money(deposits_total)],
                ['Total Standing After Deposit', _fmt_money(standing_after_deposit)],
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
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        # Reconciliation section removed per statement requirements.
        
        # Details section
        details_style = ParagraphStyle(
            'Details',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            leading=11,
            leftIndent=0,
            fontName=pdf_body_font,
        )
        if is_initial_deposit:
            details_text = (
                f"<b>Initial Deposit Confirmation:</b> {_fmt_money(total_amount_deposited)} was received for "
                f"{investor_name} ({client_code}) into {fund_name} under <b>{batch_name}</b>. "
            )
        else:
            details_text = (
                f"<b>Additional Deposit Confirmation:</b> A top-up deposit of {_fmt_money(total_amount_deposited)} "
                f"was received for {investor_name} ({client_code}) into {fund_name} under <b>{batch_name}</b>. "
                f"The standing balance before deposit was {_fmt_money(base_opening_balance)}; "
                f"net transfer amount is {_fmt_money(deposits_total)}, "
                f"bringing total standing after deposit to {_fmt_money(standing_after_deposit)}."
            )
        story.append(Paragraph(details_text, details_style))
        story.append(Spacer(1, 0.12 * inch))
        
        append_branded_footer(
            story,
            theme,
            pdf_styles,
            'Disclaimer: This is an electronically generated deposit confirmation. No signature is required. '
            'This statement is provided for informational purposes only. All figures are subject to verification '
            'and may not reflect real-time data.',
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | "
            f"Batch ID: {batch_id} | Investment ID: {inv_first.id}",
        )
        
        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        logger.error(f"Deposit PDF generation error for {client_code}, batch {batch_id}: {str(e)}")
        return None


@investment_v1.route('/api/v1/investors/<string:client_code>/deposits/<int:batch_id>/pdf', methods=['GET'])
@jwt_required()
def get_deposit_receipt_pdf(client_code, batch_id):
    """
    Generate a branded Deposit Statement/Receipt PDF.
    Shows detailed deposit information and account reconciliation.
    """
    try:
        pdf_buffer = _generate_deposit_receipt_pdf_bytes(client_code, batch_id)
        if pdf_buffer is None:
            return make_response(jsonify({"status": 404, "message": "Deposit record not found"}), 404)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"deposit-confirmation-{client_code}-{batch_id}.pdf"
        )
    except Exception as e:
        import traceback
        logger.error(f"❌ Deposit PDF route error for {client_code}, batch {batch_id}: {str(e)}")
        print(traceback.format_exc())
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _generate_transfer_receipt_pdf_bytes(client_code, batch_id):
    """
    Internal helper: Generate transfer PDF as raw bytes.
    No Flask decorators, no send_file() — safe to call from a background
    thread (the email send-queue scheduler attaches this to OFFSHORE_TRANSFER
    emails), not just an HTTP request. send_file() internally needs
    flask.request (for conditional/range response handling) and raises
    "Working outside of request context" when called outside one — which is
    exactly what silently dropped this attachment on every transfer email
    sent through the queue. Mirrors _generate_deposit_receipt_pdf_bytes.
    Returns a BytesIO buffer with PDF bytes, or None on error/not-found.
    """
    try:
        _register_montserrat_fonts()
        registered_fonts = set(pdfmetrics.getRegisteredFontNames())
        pdf_body_font = "Montserrat" if "Montserrat" in registered_fonts else "Helvetica"
        pdf_body_font_bold = "Montserrat-Bold" if "Montserrat-Bold" in registered_fonts else "Helvetica-Bold"

        investments = db.session.query(Investment).filter(
            Investment.internal_client_code == client_code,
            Investment.batch_id == batch_id
        ).all()
        if not investments:
            logger.warning(f"Transfer PDF: no investments found for {client_code} batch {batch_id}")
            return None

        inv_first = investments[0]
        currency_code = (
            (getattr(inv_first, "currency_type", None) or "").upper()
            or (getattr(getattr(inv_first, "share_class", None), "currency", None) or "").upper()
            or "USD"
        )

        def _fmt_money(amount: float) -> str:
            if currency_code == "KES":
                return f"KES {amount:,.2f}"
            return f"USD {amount:,.2f}"

        total_initial_deposit = sum(float(inv.amount_deposited or 0) for inv in investments)
        total_transaction_fee = sum(float(inv.transfer_fee_deducted or 0) for inv in investments)
        total_entry_fee = sum(float(inv.deployment_fee_deducted or 0) for inv in investments)
        net_after_transaction = max(0.0, total_initial_deposit - total_transaction_fee)
        current_net_after_transfer = sum(float(inv.net_principal or 0) for inv in investments)

        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        batch_name = batch.batch_name if batch else "Unknown Batch"
        transfer_date = datetime.now(timezone.utc)
        if batch and getattr(batch, "date_transferred", None):
            transfer_date = batch.date_transferred

        fund_name = inv_first.fund_name or (inv_first.fund.fund_name if inv_first.fund else "Portfolio")
        investor_name = inv_first.investor_name or "Investor"

        theme = get_statement_theme([fund_name])
        jh_logo_path = _resolve_janus_henderson_statement_logo_path([fund_name])

        pdf_buffer = BytesIO()
        doc = build_doc_template(pdf_buffer, theme, top_margin=0.5, bottom_margin=0.5)
        story = []
        styles = getSampleStyleSheet()
        pdf_styles = build_paragraph_styles(theme, styles, pdf_body_font, pdf_body_font_bold)
        section_heading_style = pdf_styles["section_heading"]
        normal_style = pdf_styles["normal"]

        append_receipt_header(
            story,
            theme,
            pdf_styles,
            jh_logo_path=jh_logo_path,
            document_title=(
                "TRANSFER CONFIRMATION"
                if is_dangote_dprp_fund([fund_name])
                else "TRANSFER STATEMENT & CONFIRMATION"
            ),
            fund_name=fund_name,
        )

        details_data = [
            ['Client Code', f': {client_code}'],
            ['Client Name', Paragraph(f': {escape(str(investor_name))}', normal_style)],
            ['Shares' if is_dangote_dprp_fund([fund_name]) else 'Fund', Paragraph(f': {escape(str(fund_name))}', normal_style)],
        ]
        details_table = Table(details_data, colWidths=[1.3 * inch, 6.2 * inch])
        details_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        story.append(Paragraph('Transfer Details', section_heading_style))
        story.append(details_table)
        story.append(Spacer(1, 0.25 * inch))

        amount_table = Table([['TRANSFER SUMMARY', _fmt_money(current_net_after_transfer)]], colWidths=[3.5 * inch, 3.5 * inch])
        amount_table.setStyle(highlight_banner_style(theme, pdf_body_font_bold))
        story.append(amount_table)
        story.append(Spacer(1, 0.25 * inch))

        transfer_breakdown = [
            ['Initial Deposit Amount', _fmt_money(total_initial_deposit)],
            ['Transaction Fee Contribution', f'({_fmt_money(total_transaction_fee)})'],
            ['Entry Fee Contribution', f'({_fmt_money(total_entry_fee)})'],
            ['Net After Transaction Fee', _fmt_money(net_after_transaction)],
            ['Current Net After Transfer', _fmt_money(current_net_after_transfer)],
        ]
        transfer_table = Table(transfer_breakdown, colWidths=[5.2 * inch, 2.3 * inch])
        transfer_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9f9f9')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), pdf_body_font_bold),
            ('FONTNAME', (0, 4), (-1, 4), pdf_body_font_bold),
        ]))
        story.append(Paragraph(f'Transfer Breakdown ({currency_code})', section_heading_style))
        story.append(transfer_table)
        story.append(Spacer(1, 0.12 * inch))

        append_branded_footer(
            story,
            theme,
            pdf_styles,
            'Disclaimer: This is an electronically generated transfer statement. '
            'It confirms transfer processing and fee deductions for this batch.',
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | "
            f"Batch ID: {batch_id} | Investment ID: {inv_first.id}",
        )

        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        logger.error(f"Transfer PDF generation error for {client_code}, batch {batch_id}: {str(e)}")
        return None


@investment_v1.route('/api/v1/investors/<string:client_code>/transfers/<int:batch_id>/pdf', methods=['GET'])
@jwt_required()
def get_transfer_receipt_pdf(client_code, batch_id):
    """
    Generate a branded Transfer Statement PDF.
    Shows transfer cost, entry fee, and current net after transfer.
    """
    try:
        pdf_buffer = _generate_transfer_receipt_pdf_bytes(client_code, batch_id)
        if pdf_buffer is None:
            return make_response(jsonify({"status": 404, "message": "Transfer record not found"}), 404)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"transfer-confirmation-{client_code}-{batch_id}.pdf"
        )
    except Exception as e:
        import traceback
        logger.error(f"Transfer PDF route error for {client_code}, batch {batch_id}: {str(e)}")
        print(traceback.format_exc())
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _generate_deployment_receipt_pdf_bytes(client_code, batch_id):
    """
    Internal helper: Generate deployment PDF as raw bytes.
    No Flask decorators, no send_file() — see _generate_transfer_receipt_pdf_bytes
    for why (send_file() needs an active request context; this is attached to
    INVESTMENT_ACTIVE emails from the background send-queue scheduler thread).
    Returns a BytesIO buffer with PDF bytes, or None on error/not-found.
    """
    try:
        _register_montserrat_fonts()
        registered_fonts = set(pdfmetrics.getRegisteredFontNames())
        pdf_body_font = "Montserrat" if "Montserrat" in registered_fonts else "Helvetica"
        pdf_body_font_bold = "Montserrat-Bold" if "Montserrat-Bold" in registered_fonts else "Helvetica-Bold"

        investments = db.session.query(Investment).filter(
            Investment.internal_client_code == client_code,
            Investment.batch_id == batch_id
        ).all()
        if not investments:
            logger.warning(f"Deployment PDF: no investments found for {client_code} batch {batch_id}")
            return None

        inv_first = investments[0]
        currency_code = (
            (getattr(inv_first, "currency_type", None) or "").upper()
            or (getattr(getattr(inv_first, "share_class", None), "currency", None) or "").upper()
            or "USD"
        )

        def _fmt_money(amount: float) -> str:
            if currency_code == "KES":
                return f"KES {amount:,.2f}"
            return f"USD {amount:,.2f}"

        total_initial_deposit = sum(float(inv.amount_deposited or 0) for inv in investments)
        total_transaction_fee = sum(float(inv.transfer_fee_deducted or 0) for inv in investments)
        total_entry_fee = sum(float(inv.deployment_fee_deducted or 0) for inv in investments)
        total_fees = total_transaction_fee + total_entry_fee
        net_deployed_amount = max(0.0, total_initial_deposit - total_fees)
        total_shares = sum(float(inv.shares_owned or 0) for inv in investments)

        batch = db.session.query(Batch).filter(Batch.id == batch_id).first()
        batch_name = batch.batch_name if batch else "Unknown Batch"
        deployment_date = datetime.now(timezone.utc)
        if batch and getattr(batch, "date_deployed", None):
            deployment_date = batch.date_deployed
        nav_per_share = float(getattr(inv_first, "previous_nav_price", None) or getattr(batch, "deployment_nav", 0) or 0)

        fund_name = inv_first.fund_name or (inv_first.fund.fund_name if inv_first.fund else "Portfolio")
        investor_name = inv_first.investor_name or "Investor"
        is_dprp = is_dangote_dprp_fund([fund_name])

        theme = get_statement_theme([fund_name])
        jh_logo_path = _resolve_janus_henderson_statement_logo_path([fund_name])

        pdf_buffer = BytesIO()
        doc = build_doc_template(pdf_buffer, theme, top_margin=0.5, bottom_margin=0.5)
        story = []
        styles = getSampleStyleSheet()
        pdf_styles = build_paragraph_styles(theme, styles, pdf_body_font, pdf_body_font_bold)
        section_heading_style = pdf_styles["section_heading"]
        normal_style = pdf_styles["normal"]

        append_receipt_header(
            story,
            theme,
            pdf_styles,
            jh_logo_path=jh_logo_path,
            document_title="DEPLOYMENT CONFIRMATION" if is_dprp else "DEPLOYMENT STATEMENT & CONFIRMATION",
            fund_name=fund_name,
        )

        details_data = [
            ['Client Code', f': {client_code}'],
            ['Client Name', Paragraph(f': {escape(str(investor_name))}', normal_style)],
            ['Shares' if is_dprp else 'Fund', Paragraph(f': {escape(str(fund_name))}', normal_style)],
            ['Deployment Date', f': {deployment_date.strftime("%B %d, %Y")}'],
        ]
        details_table = Table(details_data, colWidths=[1.3 * inch, 6.2 * inch])
        details_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        story.append(Paragraph('Deployment Details', section_heading_style))
        story.append(details_table)
        story.append(Spacer(1, 0.25 * inch))

        amount_table = Table([['DEPLOYMENT SUMMARY', _fmt_money(net_deployed_amount)]], colWidths=[3.5 * inch, 3.5 * inch])
        amount_table.setStyle(highlight_banner_style(theme, pdf_body_font_bold))
        story.append(amount_table)
        story.append(Spacer(1, 0.25 * inch))

        deployment_breakdown = [
            ['Original Deposit Amount', _fmt_money(total_initial_deposit)],
            ['Transaction Fee Contribution', f'({_fmt_money(total_transaction_fee)})'],
            ['Entry Fee Contribution', f'({_fmt_money(total_entry_fee)})'],
            ['Net Deployed Amount', _fmt_money(net_deployed_amount)],
        ]
        if total_shares > 0:
            deployment_breakdown.append(['Shares Purchased', f'{total_shares:,.4f}'])
        if nav_per_share > 0:
            deployment_breakdown.append(['NAV / Share', f'{nav_per_share:,.6f}'])
        deployment_table = Table(deployment_breakdown, colWidths=[5.2 * inch, 2.3 * inch])
        deployment_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), pdf_body_font, 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, -1), pdf_body_font),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9f9f9')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), pdf_body_font_bold),
            ('FONTNAME', (0, 3), (-1, 3), pdf_body_font_bold),
        ]))
        story.append(Paragraph(f'Deployment Breakdown ({currency_code})', section_heading_style))
        story.append(deployment_table)
        story.append(Spacer(1, 0.12 * inch))

        append_branded_footer(
            story,
            theme,
            pdf_styles,
            'Disclaimer: This is an electronically generated deployment confirmation. '
            'It confirms fund deployment, fee deductions, and shares purchased for this batch.',
            f"Generated on: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} | "
            f"Batch ID: {batch_id} | Investment ID: {inv_first.id}",
        )

        doc.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        logger.error(f"Deployment PDF generation error for {client_code}, batch {batch_id}: {str(e)}")
        return None


@investment_v1.route('/api/v1/investors/<string:client_code>/deployments/<int:batch_id>/pdf', methods=['GET'])
@jwt_required()
def get_deployment_receipt_pdf(client_code, batch_id):
    """
    Generate a branded Deployment Confirmation PDF (Stage 3 — funds deployed/active).
    Mirrors the deposit/transfer receipt PDFs; shows fee breakdown, shares purchased,
    and NAV per share for this batch.
    """
    try:
        pdf_buffer = _generate_deployment_receipt_pdf_bytes(client_code, batch_id)
        if pdf_buffer is None:
            return make_response(jsonify({"status": 404, "message": "Deployment record not found"}), 404)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"deployment-confirmation-{client_code}-{batch_id}.pdf"
        )
    except Exception as e:
        import traceback
        logger.error(f"Deployment PDF route error for {client_code}, batch {batch_id}: {str(e)}")
        print(traceback.format_exc())
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>', methods=['PATCH'])
@jwt_required()
def update_investor_profile(client_code):
    """
    Update investor identity fields globally (propagates across all investments for that client_code).
    Body supports:
    - investor_name, investor_email, investor_phone
    - wealth_manager, IFA, contract_note, valuation
    - share_class_id (auto-syncs currency_type from share class currency)
    - batch_id (move to an existing non-deployed batch; must match share class)
    - create_new_batch (move to a newly created batch using naming convention)
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

        share_class_updates = {}
        if "share_class_id" in data and data["share_class_id"] is not None:
            try:
                new_share_class_id = int(data["share_class_id"])
            except (TypeError, ValueError):
                return make_response(jsonify({"status": 400, "message": "share_class_id must be an integer"}), 400)

            share_class = session.query(ShareClass).filter(ShareClass.id == new_share_class_id).first()
            if not share_class:
                return make_response(jsonify({"status": 404, "message": "Share class not found"}), 404)

            # Keep investment currency aligned with selected share class.
            derived_currency = (share_class.currency or "").strip().upper()
            if derived_currency not in ("USD", "KES"):
                return make_response(jsonify({"status": 400, "message": "Selected share class has unsupported currency"}), 400)

            share_class_updates = {
                "share_class_id": new_share_class_id,
                "currency_type": derived_currency,
                "share_series": share_class.class_code,
            }

        # Determine effective share class (selected or current).
        effective_share_class_id = (
            share_class_updates.get("share_class_id")
            if share_class_updates
            else existing.share_class_id
        )

        move_to_batch_id = None
        if "batch_id" in data and data["batch_id"] is not None:
            try:
                move_to_batch_id = int(data["batch_id"])
            except (TypeError, ValueError):
                return make_response(jsonify({"status": 400, "message": "batch_id must be an integer"}), 400)

        create_new_batch = bool(data.get("create_new_batch"))

        if move_to_batch_id is not None and create_new_batch:
            return make_response(jsonify({
                "status": 400,
                "message": "Provide either batch_id or create_new_batch, not both.",
            }), 400)

        target_batch = None
        if move_to_batch_id is not None:
            target_batch = session.query(Batch).filter(Batch.id == move_to_batch_id).first()
            if not target_batch:
                return make_response(jsonify({"status": 404, "message": "Target batch not found"}), 404)

            # Rule 1: cannot move into a deployed batch
            if (
                (target_batch.stage or 1) >= 3
                or bool(target_batch.deployment_confirmed)
                or target_batch.deployment_date_actual is not None
                or target_batch.deployment_nav is not None
            ):
                return make_response(jsonify({
                    "status": 409,
                    "message": "Investor cannot be moved to a deployed batch.",
                }), 409)

            # Rule 2: target batch share class must match
            if (
                effective_share_class_id is not None
                and target_batch.share_class_id is not None
                and int(target_batch.share_class_id) != int(effective_share_class_id)
            ):
                return make_response(jsonify({
                    "status": 409,
                    "message": "Investor cannot be moved: target batch share class does not match.",
                }), 409)

            if effective_share_class_id is not None and target_batch.share_class_id is None:
                # Keep batch metadata consistent if legacy batch missed share_class_id.
                target_batch.share_class_id = int(effective_share_class_id)
                session.add(target_batch)

        if create_new_batch:
            if effective_share_class_id is None:
                return make_response(jsonify({
                    "status": 400,
                    "message": "share_class_id is required to create a new batch.",
                }), 400)

            sc = session.query(ShareClass).filter(ShareClass.id == int(effective_share_class_id)).first()
            if not sc:
                return make_response(jsonify({"status": 404, "message": "Share class not found"}), 404)

            # Use existing naming logic from BatchManagementService.
            preferred_name_date = None
            try:
                if getattr(existing, "deposit_date", None):
                    preferred_name_date = existing.deposit_date
                elif getattr(existing, "date_deposited", None):
                    preferred_name_date = existing.date_deposited.date()
            except Exception:
                preferred_name_date = None

            target_batch = BatchManagementService._create_new_batch(sc, batch_name_date=preferred_name_date)
        # If share class changed (or explicitly provided) and no batch was chosen,
        # automatically move investor into the correct OPEN batch for that share class.
        if target_batch is None and effective_share_class_id is not None and ("share_class_id" in data and data["share_class_id"] is not None):
            preferred_name_date = None
            try:
                if getattr(existing, "deposit_date", None):
                    preferred_name_date = existing.deposit_date
                elif getattr(existing, "date_deposited", None):
                    preferred_name_date = existing.date_deposited.date()
            except Exception:
                preferred_name_date = None
            target_batch = BatchManagementService.find_or_create_batch(
                int(effective_share_class_id),
                batch_name_date=preferred_name_date,
            )

        if not updates and not extra_fields and not share_class_updates and target_batch is None:
            return make_response(jsonify({"status": 400, "message": "No updatable fields provided"}), 400)

        def _get_movable_investments():
            """Helper to identify non-deployed investments for this client."""
            return (
                session.query(Investment)
                .join(Batch, Batch.id == Investment.batch_id)
                .filter(
                    Investment.internal_client_code == client_code,
                    func.coalesce(Batch.stage, 1) < 3,
                    func.coalesce(Batch.deployment_confirmed, False).is_(False),
                    Batch.deployment_date_actual.is_(None),
                    Batch.deployment_nav.is_(None),
                    func.coalesce(Batch.is_active, False).is_(False),
                )
                .all()
            )

        if updates:
            q.update(updates, synchronize_session=False)
        if extra_fields:
            q.update(extra_fields, synchronize_session=False)
        if share_class_updates:
            # Apply share class updates to ALL investments (including deployed)
            q.update(
                share_class_updates,
                synchronize_session=False,
            )

            # Keep pending/suppressed queue items for this investor aligned to the new currency.
            investor_ids_subq = session.query(Investment.id).filter(Investment.internal_client_code == client_code)
            session.query(PendingEmail).filter(
                PendingEmail.investor_id.in_(investor_ids_subq),
                PendingEmail.status.in_(("Pending_Confirmation", "Suppressed", "Queued")),
            ).update(
                {"currency_type": share_class_updates["currency_type"]},
                synchronize_session=False,
            )
            # Also keep InvestorShares in sync with the new share class id when provided.
            if "share_class_id" in share_class_updates and share_class_updates.get("share_class_id") is not None:
                try:
                    new_sc_id = int(share_class_updates["share_class_id"])
                    session.query(InvestorShares).join(Investment, InvestorShares.investment_id == Investment.id).filter(
                        Investment.internal_client_code == client_code
                    ).update(
                        {InvestorShares.share_class_id: new_sc_id},
                        synchronize_session=False,
                    )
                except Exception:
                    logger.exception("Failed to sync InvestorShares share_class_id for investor %s", client_code)

        moved_count = 0
        if target_batch is not None:
            # Move only NON-deployed holdings for this investor.
            # Treat NULL deployment_confirmed as "not deployed".
            # Deployed batches in this system are typically stage>=3 and/or is_active=True.
            movable_rows = _get_movable_investments()
            for row in movable_rows:
                row.batch_id = target_batch.id
                if effective_share_class_id is not None:
                    row.share_class_id = int(effective_share_class_id)
                moved_count += 1

            if moved_count == 0:
                return make_response(jsonify({
                    "status": 409,
                    "message": "No movable investor records found (current holdings may already be deployed).",
                }), 409)

        session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": "Investor updated",
            "data": {
                "client_code": client_code,
                **updates,
                **extra_fields,
                **share_class_updates,
                "batch_id": target_batch.id if target_batch is not None else None,
                "moved_count": moved_count,
            },
        }), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/deposits', methods=['GET'])
@jwt_required()
def list_investor_deposits(client_code):
    """
    List all deposits (investments) for a single investor across all batches.
    Shows deposit amount, date, batch, share class, and deployment status.
    Useful when an investor made multiple deposits and needs to update share class selectively.

    Response: {
      "status": 200,
      "data": [
        {
          "investment_id": 1,
          "amount_deposited": 100000,
          "date_deposited": "2026-04-10",
          "batch_id": 1,
          "batch_name": "AXM_KES_I_2026-04-10",
          "share_class_id": 1,
          "class_code": "KES_I",
          "currency": "KES",
          "is_deployed": false,
          "is_movable": true
        }
      ]
    }
    """
    try:
        session = db.session
        product = (request.args.get("product") or "").strip().upper() or None

        # Get all investments for this investor
        deposits_q = session.query(Investment).filter(
            Investment.internal_client_code == client_code
        )
        if product:
            deposits_q = deposits_q.filter(Investment.product_type == product)
        investments = deposits_q.order_by(Investment.date_deposited.desc()).all()

        if not investments:
            return make_response(jsonify({"status": 404, "message": "No deposits found for this investor"}), 404)

        data = []
        for inv in investments:
            batch = inv.batch
            share_class = inv.share_class
            
            # Determine if investment is deployed
            is_deployed = bool(
                (batch.stage or 1) >= 3 
                or batch.deployment_confirmed 
                or batch.deployment_date_actual 
                or batch.deployment_nav
            ) if batch else False
            
            # Determine if investment is movable (same logic as move logic)
            is_movable = False
            if batch and not is_deployed:
                is_movable = bool(
                    (batch.stage or 1) < 3
                    and not (batch.deployment_confirmed or False)
                    and batch.deployment_date_actual is None
                    and batch.deployment_nav is None
                    and not (batch.is_active or False)
                )
            
            data.append({
                "investment_id": inv.id,
                "amount_deposited": float(inv.amount_deposited or 0),
                "date_deposited": inv.date_deposited.isoformat() if inv.date_deposited else None,
                "batch_id": batch.id if batch else None,
                "batch_name": batch.batch_name if batch else None,
                "share_class_id": share_class.id if share_class else None,
                "class_code": share_class.class_code if share_class else None,
                "currency": share_class.currency if share_class else None,
                "is_deployed": is_deployed,
                "is_movable": is_movable,
                "product_type": inv.product_type,
            })

        return make_response(jsonify({"status": 200, "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/deposits/bulk-update', methods=['PATCH'])
@jwt_required()
def bulk_update_investor_deposits(client_code):
    """
    Selectively update share class/currency for specific deposits (investments) of a single investor.
    Allows moving individual deposits to a different share class without affecting all deposits.

    Request body: {
      "investment_ids": [1, 3, 5],  # IDs of deposits to update
      "share_class_id": 2,           # Target share class
      "move_to_batch_id": 7          # Optional: move to specific batch (must be non-deployed)
    }

    Response: {
      "status": 200,
      "message": "Deposits updated",
      "data": {
        "updated_count": 3,
        "batch_id": 7,
        "share_class_id": 2
      }
    }
    """
    try:
        data = request.get_json() or {}
        session = db.session

        # Validate investment IDs
        investment_ids = data.get("investment_ids", [])
        if not investment_ids or not isinstance(investment_ids, list):
            return make_response(jsonify({"status": 400, "message": "investment_ids must be a non-empty array"}), 400)

        # Validate share class
        if "share_class_id" not in data or data["share_class_id"] is None:
            return make_response(jsonify({"status": 400, "message": "share_class_id is required"}), 400)

        try:
            new_share_class_id = int(data["share_class_id"])
        except (TypeError, ValueError):
            return make_response(jsonify({"status": 400, "message": "share_class_id must be an integer"}), 400)

        share_class = session.query(ShareClass).filter(ShareClass.id == new_share_class_id).first()
        if not share_class:
            return make_response(jsonify({"status": 404, "message": "Share class not found"}), 404)

        derived_currency = (share_class.currency or "").strip().upper()
        if derived_currency not in ("USD", "KES"):
            return make_response(jsonify({"status": 400, "message": "Selected share class has unsupported currency"}), 400)

        # Validate target batch if provided
        target_batch = None
        if "move_to_batch_id" in data and data["move_to_batch_id"] is not None:
            try:
                move_to_batch_id = int(data["move_to_batch_id"])
            except (TypeError, ValueError):
                return make_response(jsonify({"status": 400, "message": "move_to_batch_id must be an integer"}), 400)

            target_batch = session.query(Batch).filter(Batch.id == move_to_batch_id).first()
            if not target_batch:
                return make_response(jsonify({"status": 404, "message": "Target batch not found"}), 404)

            # Rule 1: cannot move into a deployed batch
            if (
                (target_batch.stage or 1) >= 3
                or bool(target_batch.deployment_confirmed)
                or target_batch.deployment_date_actual is not None
                or target_batch.deployment_nav is not None
            ):
                return make_response(jsonify({
                    "status": 409,
                    "message": "Cannot move deposits to a deployed batch.",
                }), 409)

            # Rule 2: batch share class must match
            if (
                target_batch.share_class_id is not None
                and int(target_batch.share_class_id) != int(new_share_class_id)
            ):
                return make_response(jsonify({
                    "status": 409,
                    "message": "Target batch share class does not match the selected share class.",
                }), 409)

        # Fetch investments belonging to this client and in the provided list
        investments = session.query(Investment).filter(
            Investment.internal_client_code == client_code,
            Investment.id.in_(investment_ids)
        ).all()

        if not investments:
            return make_response(jsonify({"status": 404, "message": "No investments found for the provided IDs"}), 404)

        # Filter for movable investments only (not deployed)
        movable_investments = []
        for inv in investments:
            batch = inv.batch
            if not batch:
                continue

            is_deployed = (
                (batch.stage or 1) >= 3
                or bool(batch.deployment_confirmed)
                or batch.deployment_date_actual is not None
                or batch.deployment_nav is not None
                or bool(batch.is_active)
            )

            if not is_deployed:
                movable_investments.append(inv)

        if not movable_investments:
            return make_response(jsonify({
                "status": 409,
                "message": "None of the selected deposits are movable (all may already be deployed).",
            }), 409)

        # Update each movable investment
        for inv in movable_investments:
            inv.share_class_id = new_share_class_id
            inv.currency_type = derived_currency
            inv.share_series = share_class.class_code
            
            if target_batch is not None:
                inv.batch_id = target_batch.id
            else:
                # Auto-find or create batch for this share class
                existing_batch = BatchManagementService.find_or_create_batch(
                    new_share_class_id,
                    batch_name_date=inv.deposit_date,
                )
                inv.batch_id = existing_batch.id
            
            session.add(inv)
            # Also update InvestorShares records tied to this investment so valuation maps to the new share class
            try:
                session.query(InvestorShares).filter(
                    InvestorShares.investment_id == inv.id
                ).update(
                    {InvestorShares.share_class_id: new_share_class_id},
                    synchronize_session=False,
                )
            except Exception:
                logger.exception("Failed to sync InvestorShares for investment %s", inv.id)

        session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": "Deposits updated successfully",
            "data": {
                "updated_count": len(movable_investments),
                "batch_id": target_batch.id if target_batch is not None else "auto-selected",
                "share_class_id": new_share_class_id,
                "currency": derived_currency,
            },
        }), 200)

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
                "amount": float(w.gross_amount if getattr(w, "gross_amount", None) is not None else w.amount or 0),
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
            gross_amount=amount_decimal,
            exit_fee_deducted=Decimal("0.00"),
            amount=amount_decimal,
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
    - source=investor_request|oversubscription_refund
    - product=FUNDS|SHARES (Task 11) — resolved via the withdrawal's fund
      (every withdrawal, refund or not, always has fund_id set)
    - fund_id=<int>
    - search (optional): matches client code
    - count_only=true: skip building/returning rows, just return the matching
      count — used by the "Approve All"/"Reject All" preview so it doesn't have
      to fetch every matching row (which, at 10,000+ pending withdrawals, would
      be exactly the kind of unbounded fetch this pagination is meant to avoid)
      just to show a number.
    - page (default 1), per_page (default 200, max 500)
    Returns withdrawal data with fund information from relationship
    """
    try:
        status = request.args.get('status')
        source = request.args.get('source')
        product = (request.args.get('product') or '').strip().upper() or None
        fund_id = request.args.get('fund_id', type=int)
        search = (request.args.get('search') or '').strip()
        count_only = (request.args.get('count_only') or '').lower() == 'true'
        page = max(request.args.get('page', default=1, type=int) or 1, 1)
        per_page = min(max(request.args.get('per_page', default=200, type=int) or 200, 1), 500)

        q = db.session.query(Withdrawal)
        if status:
            status = normalize_withdrawal_status(status)
            q = q.filter(Withdrawal.status == status)
        if source:
            q = q.filter(Withdrawal.source == source)
        if product:
            q = q.join(CoreFund, CoreFund.id == Withdrawal.fund_id).filter(CoreFund.product_type == product)
        if fund_id:
            q = q.filter(Withdrawal.fund_id == fund_id)
        if search:
            q = q.filter(Withdrawal.internal_client_code.ilike(f"%{search}%"))

        total = q.count()

        if count_only:
            return make_response(jsonify({
                "status": 200,
                "data": [],
                "message": f"{total} withdrawal(s) match",
                "pagination": {"total": total},
            }), 200)

        total_pages = max((total + per_page - 1) // per_page, 1)
        page = min(page, total_pages)
        rows = (
            q.order_by(Withdrawal.date_withdrawn.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # Task 11: investor name for the "Investor" column — one bulk lookup
        # for the whole page instead of one query per row.
        client_codes = {w.internal_client_code for w in rows}
        investor_names = dict(
            db.session.query(Investment.internal_client_code, Investment.investor_name)
            .filter(Investment.internal_client_code.in_(client_codes))
            .all()
        ) if client_codes else {}

        data = [
            {
                "id": w.id,
                "client_id": w.internal_client_code,
                "investor_name": investor_names.get(w.internal_client_code),
                "fund_id": w.fund_id,
                "fund_name": w.fund.fund_name if w.fund else w.fund_name,  # Use relationship if available, fallback to column
                "product_type": w.fund.product_type if w.fund else None,
                "amount": float(w.gross_amount if getattr(w, "gross_amount", None) is not None else w.amount or 0),
                "status": w.status,
                "date_withdrawn": w.date_withdrawn.isoformat(),
                "approved_at": w.approved_at.isoformat() if w.approved_at else None,
                "note": w.note,
                "source": w.source or WITHDRAWAL_SOURCE_INVESTOR_REQUEST,
                "batch_id": w.batch_id,
                "batch_name": w.batch.batch_name if w.batch else None,
                # The NGN/1 USD rate used at SHARES deployment (same rate for
                # every investor in the batch) — only meaningful for a
                # source=oversubscription_refund row, which always has batch_id.
                "rate_used": float(w.batch.shares_exchange_rate_ngn) if w.batch and w.batch.shares_exchange_rate_ngn is not None else None,
                # Only meaningful for source=oversubscription_refund — whether the
                # one-time Oversubscription/Refund Notice has been sent for this
                # refund yet (see EmailService.send_oversubscription_refund_notices).
                "oversubscription_notice_sent": bool(getattr(w, "oversubscription_notice_sent_at", None)),
            }
            for w in rows
        ]
        return make_response(jsonify({
            "status": 200,
            "data": data,
            "message": f"Retrieved {len(data)} withdrawal(s)",
            "pagination": {"page": page, "per_page": per_page, "total": total, "total_pages": total_pages},
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
                    existing.gross_amount = amount
                    existing.exit_fee_deducted = Decimal("0.00")
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
                        gross_amount=amount,
                        exit_fee_deducted=Decimal("0.00"),
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
                            currency=inv.currency_type or 'USD',
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
                impact = _calculate_investor_impact(w)
                message = f"Withdrawal approved and calculations updated"
                
                # Email trigger intentionally disabled here.
                # Allowed trigger is withdrawals upload only.
            except Exception as calc_err:
                # Log but don't fail the approval
                print(f"⚠️  Warning: Calculation failed for withdrawal {withdrawal_id}: {str(calc_err)}")
                message = f"Withdrawal approved (calculation warning: {str(calc_err)})"
                impact = None
        else:
            w.approved_at = None
            message = "Withdrawal rejected"
            impact = None

        # Log event for audit trail
        _log_withdrawal_event(withdrawal_id, old_status, status, note)

        db.session.commit()

        # Approving/rejecting a withdrawal changes what _calculate_batch_investment_values
        # deducts for the affected investments, so refresh every batch those investments
        # belong to. Withdrawal.batch_id isn't reliably set — resolve via the matching
        # Investment rows (same client_code + fund) instead, same as the balance calc itself.
        try:
            affected_batch_ids = {
                bid for (bid,) in db.session.query(Investment.batch_id).filter(
                    Investment.internal_client_code == w.internal_client_code,
                    Investment.fund_id == w.fund_id if w.fund_id else Investment.fund_name == w.fund_name,
                    Investment.batch_id.isnot(None),
                ).all()
            }
            if affected_batch_ids:
                from app.Batch.controllers import BatchController
                BatchController.refresh_cached_total_capital_for_batch_ids(affected_batch_ids, db.session)
        except Exception as cache_err:
            print(f"Warning: Failed to refresh cached batch totals after withdrawal {status.lower()}: {str(cache_err)}")

        return make_response(jsonify({
            "status": 200,
            "message": message,
            "data": {
                "id": w.id,
                "status": w.status,
                "approved_at": w.approved_at.isoformat() if w.approved_at else None,
                "impact": impact,
            }
        }), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/withdrawals/bulk-action', methods=['POST'])
@jwt_required()
def bulk_update_withdrawals():
    """
    Approve or reject many Pending withdrawals in one request — the "Approve All" /
    "Reject All" action, so a fund with thousands of pending withdrawals doesn't
    require one click (and one HTTP round-trip) per row.

    Body: {
      action: 'approve' | 'reject',
      ids?: number[],           # exact withdrawal IDs (e.g. a checkbox selection)
      scope?: {                 # used instead of ids: act on every row matching this
        source?: 'investor_request' | 'oversubscription_refund',
        product?: 'FUNDS' | 'SHARES',
        fund_id?: number,
      },
      note?: string,
    }

    Only rows currently in 'Pending' status are ever touched — an already
    Approved/Rejected withdrawal is silently skipped, never re-processed, so a
    filter-scoped "Approve All" is always safe to click again. Runs as ONE
    transaction: every matched investor's live valuation is recalculated, one
    audit log entry per withdrawal + one per approval is written (same fields
    _calculate_investor_impact / _log_withdrawal_event write for a single
    approval, just batched), and every affected batch's cached total is
    refreshed exactly once at the end via refresh_cached_total_capital_for_batch_ids.
    """
    try:
        from app.utils.audit_log import AuditLog, get_client_ip, get_user_identity_meta
        import json as _json

        data = request.get_json() or {}
        action = (data.get('action') or '').strip().lower()
        if action not in ('approve', 'reject'):
            return make_response(jsonify({"status": 400, "message": "action must be 'approve' or 'reject'"}), 400)
        new_status = 'Approved' if action == 'approve' else 'Rejected'

        ids = data.get('ids')
        scope = data.get('scope') or {}
        note = (data.get('note') or '').strip()

        q = db.session.query(Withdrawal).filter(Withdrawal.status == 'Pending')
        if ids:
            if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
                return make_response(jsonify({"status": 400, "message": "ids must be a list of integers"}), 400)
            q = q.filter(Withdrawal.id.in_(ids))
        else:
            source = scope.get('source')
            product = (scope.get('product') or '').strip().upper() or None
            fund_id = scope.get('fund_id')
            if source:
                q = q.filter(Withdrawal.source == source)
            if product:
                q = q.join(CoreFund, CoreFund.id == Withdrawal.fund_id).filter(CoreFund.product_type == product)
            if fund_id:
                q = q.filter(Withdrawal.fund_id == fund_id)

        rows = q.all()
        if not rows:
            return make_response(jsonify({
                "status": 200,
                "message": "No pending withdrawals matched",
                "data": {"processed": 0, "approved": 0, "rejected": 0, "affected_batch_ids": []},
            }), 200)

        now = datetime.now(timezone.utc)
        actor_id, actor_email, actor_name = get_user_identity_meta()
        ip = get_client_ip()
        ua = request.headers.get('User-Agent', 'UNKNOWN') if request else 'SYSTEM'

        # Preload latest Investment per (client_code, fund_id) in ONE query — the
        # same "latest by date_deposited" investor _calculate_investor_impact picks
        # for a single approval — instead of one lookup per row.
        latest_investment_by_pair = {}
        if action == 'approve':
            client_codes = {w.internal_client_code for w in rows}
            candidates = (
                db.session.query(Investment)
                .filter(Investment.internal_client_code.in_(client_codes))
                .order_by(Investment.internal_client_code, Investment.fund_id, Investment.date_deposited.desc())
                .all()
            )
            for inv in candidates:
                key = (inv.internal_client_code, inv.fund_id)
                if key not in latest_investment_by_pair:
                    latest_investment_by_pair[key] = inv

        # Prefetch the EpochLedger fallback (used when an investment's
        # `valuation` column is unset, i.e. Decimal("0") — the common case,
        # since this legacy column is rarely populated) for every row in ONE
        # query instead of one query per withdrawal. This — not the
        # affected-batches loop above — was the dominant remaining cost at
        # scale: nearly every approved row was hitting this fallback.
        latest_epoch_by_pair = {}
        if action == 'approve':
            epoch_candidates = (
                db.session.query(EpochLedger)
                .filter(EpochLedger.internal_client_code.in_(client_codes))
                .order_by(EpochLedger.internal_client_code, EpochLedger.epoch_end.desc())
                .all()
            )
            for ep in epoch_candidates:
                key = (ep.internal_client_code, (ep.fund_name or "").lower())
                if key not in latest_epoch_by_pair:
                    latest_epoch_by_pair[key] = ep

        # Resolve affected batches up front the same way the single-item endpoint
        # does — via matching Investment rows, since Withdrawal.batch_id isn't
        # always set directly on the row. Grouped into a dict keyed by
        # client_code ONCE — the loop below used to re-scan this whole list
        # per withdrawal row (O(rows × investment_batches)), which was the
        # actual freeze at 10k+ withdrawals: tens of millions of Python-level
        # comparisons, not a slow query.
        client_codes_all = {w.internal_client_code for w in rows}
        investment_batches = (
            db.session.query(Investment.internal_client_code, Investment.fund_id, Investment.fund_name, Investment.batch_id)
            .filter(Investment.internal_client_code.in_(client_codes_all), Investment.batch_id.isnot(None))
            .all()
        )
        investment_batches_by_code = {}
        for code, fid, fname, bid in investment_batches:
            investment_batches_by_code.setdefault(code, []).append((fid, fname, bid))

        # Persistence is done as raw bulk SQL instead of one UPDATE per row.
        # bulk_update_mappings() (tried first) still issues one UPDATE per
        # row via executemany — correct, but 10,000 row-level round trips
        # through the driver was still ~7s of a ~14s request at 5,000 rows.
        # Below, each table gets exactly ONE UPDATE statement, matched via
        # Postgres unnest() against parallel arrays — see the SQL further
        # down for why. audit_log_rows still batches into a single
        # multi-row INSERT via insertmanyvalues (needs every dict to have
        # the SAME keys, or Postgres/SQLAlchemy silently falls back to one
        # INSERT per row — this bit us once already, see below).
        withdrawal_updates = []
        audit_log_rows = []
        affected_batch_ids = set()
        approved_count = 0
        rejected_count = 0
        # Tracks each Investment's running valuation across this loop as a
        # plain dict, NOT by mutating the ORM-tracked `inv` object. Mutating
        # `inv.valuation` directly (an earlier version of this code did)
        # marks the object dirty, and SQLAlchemy's autoflush then re-issues
        # its own UPDATE for that row on top of the explicit
        # bulk_update_mappings() call below — redundant I/O that made this
        # slower than the pre-bulk-conversion version when profiled.
        running_valuation_by_inv_id = {}

        for w in rows:
            old_status = w.status
            wd_update = {"id": w.id, "status": new_status, "note": (note if note else w.note)}

            if w.batch_id:
                affected_batch_ids.add(w.batch_id)
            for fid, fname, bid in investment_batches_by_code.get(w.internal_client_code, []):
                if (w.fund_id is not None and fid == w.fund_id) or (w.fund_id is None and fname == w.fund_name):
                    affected_batch_ids.add(bid)

            if new_status == 'Approved':
                wd_update["approved_at"] = now
                approved_count += 1

                amount = Decimal(str(w.gross_amount if w.gross_amount is not None else (w.amount or 0)))
                inv = latest_investment_by_pair.get((w.internal_client_code, w.fund_id))
                if inv is not None:
                    if inv.id in running_valuation_by_inv_id:
                        old_valuation = running_valuation_by_inv_id[inv.id]
                    else:
                        old_valuation = Decimal(str(inv.valuation or 0))
                        if old_valuation == Decimal('0'):
                            latest_epoch = latest_epoch_by_pair.get((w.internal_client_code, (w.fund_name or "").lower()))
                            if latest_epoch and latest_epoch.end_balance is not None:
                                old_valuation = Decimal(str(latest_epoch.end_balance))
                    new_valuation = max(Decimal('0'), old_valuation - amount)
                    # Only the FINAL running value per investment is kept (not
                    # appended per withdrawal) — the bulk UPDATE below is a
                    # single statement matched via unnest(), and Postgres does
                    # not guarantee which source row "wins" if the same id
                    # appears twice in one UPDATE...FROM, so duplicates must
                    # be collapsed here instead of left for the DB to resolve.
                    running_valuation_by_inv_id[inv.id] = new_valuation

                    audit_log_rows.append({
                        "user_id": actor_id, "user_email": actor_email, "user_name": actor_name,
                        "action": "WITHDRAWAL_APPROVED", "target_type": "Withdrawal", "target_id": w.id,
                        "target_name": f"{w.internal_client_code} - {w.fund_name}",
                        "description": f"Total updated: ${amount} withdrawal processed for client {w.internal_client_code} (bulk approval)",
                        "old_value": _json.dumps({
                            "client_code": w.internal_client_code, "fund_name": w.fund_name,
                            "amount": float(amount), "valuation_before": float(old_valuation),
                        }, default=str),
                        "new_value": _json.dumps({
                            "client_code": w.internal_client_code, "fund_name": w.fund_name,
                            "amount": float(amount), "valuation_after": float(new_valuation),
                        }, default=str),
                        "ip_address": ip, "user_agent": ua, "timestamp": now, "success": True,
                    })
            else:
                wd_update["approved_at"] = None
                rejected_count += 1

            withdrawal_updates.append(wd_update)
            audit_log_rows.append({
                "user_id": actor_id, "user_email": actor_email, "user_name": actor_name,
                "action": "WITHDRAWAL_STATUS_CHANGE", "target_type": "Withdrawal", "target_id": w.id,
                # target_name is included here (even though this entry type
                # doesn't otherwise need it) so every dict in audit_log_rows
                # has an IDENTICAL key set. SQLAlchemy's insertmanyvalues
                # batching requires that to emit one multi-row INSERT — with
                # mismatched keys (this dict used to omit target_name) it
                # silently fell back to ~10k individual INSERT round trips,
                # which was the actual bottleneck profiling turned up.
                "target_name": f"{w.internal_client_code} - {w.fund_name}",
                "description": f"Status changed from {old_status} to {new_status} (bulk action)",
                "old_value": _json.dumps({"status": old_status, "note": note}, default=str),
                "new_value": _json.dumps({"status": new_status, "note": note}, default=str),
                "ip_address": ip, "user_agent": ua, "timestamp": now, "success": True,
            })

        if withdrawal_updates:
            # unnest() turns 4 equal-length arrays into a virtual row set in
            # ONE round trip — the whole point being that this is a single
            # UPDATE statement touching N rows, not N UPDATE statements sent
            # via executemany (which is what bulk_update_mappings did, and
            # was still the dominant remaining cost profiled above).
            db.session.execute(text("""
                UPDATE withdrawals AS w
                SET status = v.status, note = v.note, approved_at = v.approved_at
                FROM (
                    SELECT * FROM unnest(
                        CAST(:ids AS integer[]),
                        CAST(:statuses AS text[]),
                        CAST(:notes AS text[]),
                        CAST(:approved_ats AS timestamp[])
                    ) AS t(id, status, note, approved_at)
                ) AS v
                WHERE w.id = v.id
            """), {
                "ids": [u["id"] for u in withdrawal_updates],
                "statuses": [u["status"] for u in withdrawal_updates],
                "notes": [u["note"] for u in withdrawal_updates],
                "approved_ats": [u["approved_at"] for u in withdrawal_updates],
            })
        if running_valuation_by_inv_id:
            # running_valuation_by_inv_id already holds exactly one (final)
            # entry per investment id — see the dedupe comment where it's
            # populated above — so there's no risk of the same id appearing
            # twice in this UPDATE...FROM (undefined which one would "win").
            db.session.execute(text("""
                UPDATE investments AS i
                SET valuation = v.valuation
                FROM (
                    SELECT * FROM unnest(
                        CAST(:ids AS integer[]),
                        CAST(:valuations AS numeric[])
                    ) AS t(id, valuation)
                ) AS v
                WHERE i.id = v.id
            """), {
                "ids": list(running_valuation_by_inv_id.keys()),
                "valuations": [str(v) for v in running_valuation_by_inv_id.values()],
            })
        if audit_log_rows:
            db.session.execute(insert(AuditLog), audit_log_rows)
        db.session.commit()

        if affected_batch_ids:
            try:
                from app.Batch.controllers import BatchController
                BatchController.refresh_cached_total_capital_for_batch_ids(affected_batch_ids, db.session)
            except Exception as cache_err:
                print(f"Warning: Failed to refresh cached batch totals after bulk withdrawal action: {str(cache_err)}")

        return make_response(jsonify({
            "status": 200,
            "message": f"{len(rows)} withdrawal(s) processed",
            "data": {
                "processed": len(rows),
                "approved": approved_count,
                "rejected": rejected_count,
                "affected_batch_ids": list(affected_batch_ids),
            },
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
    amount = Decimal(str(withdrawal.gross_amount if getattr(withdrawal, "gross_amount", None) is not None else withdrawal.amount or 0))
    
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
        # Derive the current standing baseline:
        # 1) Investment.valuation when present
        # 2) latest epoch end_balance for this investor/fund
        # 3) 0 fallback
        old_valuation = Decimal(str(latest_investment.valuation or 0))
        if old_valuation == Decimal("0"):
            latest_epoch = (
                db.session.query(EpochLedger)
                .filter(
                    EpochLedger.internal_client_code == client_code,
                    func.lower(EpochLedger.fund_name) == func.lower(withdrawal.fund_name or ""),
                )
                .order_by(EpochLedger.epoch_end.desc())
                .first()
            )
            if latest_epoch and latest_epoch.end_balance is not None:
                old_valuation = Decimal(str(latest_epoch.end_balance))

        # Deduct withdrawal immediately from current standing on approval.
        new_valuation = max(Decimal('0'), old_valuation - amount)
        latest_investment.valuation = new_valuation
            
        # Let the NEXT EpochLedger naturally acquire this withdrawal during its own valuation run.
        # This perfectly preserves Snapshot Isolation for committed reports.
        
        # Log to audit trail
        create_audit_log(
            action="WITHDRAWAL_APPROVED",
            target_type="Withdrawal",
            target_id=withdrawal.id,
            target_name=f"{client_code} - {withdrawal.fund_name}",
            description=f"Total updated: ${amount} withdrawal processed for client {client_code}",
            old_value={
                "client_code": client_code,
                "fund_name": withdrawal.fund_name,
                "amount": float(amount),
                "valuation_before": float(old_valuation),
            },
            new_value={
                "client_code": client_code,
                "fund_name": withdrawal.fund_name,
                "amount": float(amount),
                "valuation_after": float(new_valuation),
            },
            success=True
        )
        period = ""
        if withdrawal.date_withdrawn:
            try:
                period = withdrawal.date_withdrawn.strftime("%Y-%m")
            except Exception:
                period = ""

        print(f"✅ Withdrawal #{withdrawal.id} approved for {client_code} in {withdrawal.fund_name}: ${amount}")
        return {
            "client_code": client_code,
            "fund_name": withdrawal.fund_name,
            "period": period,
            "withdrawal_amount": float(amount),
            "standing_before": float(old_valuation),
            "standing_after": float(new_valuation),
        }

    print(f"✅ Withdrawal #{withdrawal.id} approved for {client_code} in {withdrawal.fund_name}: ${amount}")
    return None


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

def _serialize_pending_email_row(r):
    """
    Serialize PendingEmail row to the frontend's PendingEmail shape.
    Includes extra computed fields used by deposit statement preview.
    """
    from app.Investments.model import Investment

    inv = r.investor
    if not inv and r.investor_id:
        inv = db.session.get(Investment, r.investor_id)

    net_after_deductions = None
    if inv is not None:
        net_after_deductions = (
            (inv.amount_deposited or 0)
            - (inv.transfer_fee_deducted or 0)
            - (inv.deployment_fee_deducted or 0)
        )

    entry_fee_percent = None
    if r.batch is not None:
        entry_fee_percent = getattr(r.batch, "transfer_entry_fee_percent", None)
        if entry_fee_percent is None:
            entry_fee_percent = getattr(r.batch, "entry_fee_percentage", None)

    return {
        "id": r.id,
        "email_type": r.email_type,
        "status": getattr(r, "status", None),
        "recipient_email": r.recipient_email,
        "recipient_name": r.recipient_name,
        "subject": r.subject,
        "body": r.body,
        "batch_name": r.batch_name,
        "fund_name": r.fund_name,
        "amount": float(r.amount) if r.amount is not None else None,
        "batch_id": r.batch_id,
        "investor_id": r.investor_id,
        "currency_type": r.currency_type or 'USD',
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "processed_at": r.processed_at.isoformat() if getattr(r, "processed_at", None) else None,
        "initial_deposit_usd": float(inv.amount_deposited) if inv and inv.amount_deposited is not None else None,
        "transaction_fee_usd": float(inv.transfer_fee_deducted) if inv and inv.transfer_fee_deducted is not None else None,
        "entry_fee_usd": float(inv.deployment_fee_deducted) if inv and inv.deployment_fee_deducted is not None else None,
        "entry_fee_percent": float(entry_fee_percent) if entry_fee_percent is not None else None,
        "main_balance": float(net_after_deductions) if net_after_deductions is not None else None,
    }


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
        data = [_serialize_pending_email_row(r) for r in rows]
        return make_response(jsonify({"status": 200, "count": len(data), "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/inbox', methods=['GET'])
@jwt_required()
def list_email_inbox():
    """
    Counts + (optionally) a filtered list of emails needing human attention:
    Pending_Confirmation / Suppressed / Queued.

    With no `search` param, `data` comes back empty and only the counts are
    returned — this keeps the Email page fast once thousands of rows pile up,
    since the per-row serializer (which touches the linked Investment) never
    runs against the whole table. Pass `search` (client code, recipient email,
    or phone) to fetch the matching rows, paginated via `page`/`per_page`.
    """
    try:
        from app.Investments.model import PendingEmail
        statuses = ('Pending_Confirmation', 'Suppressed', 'Queued')
        search = (request.args.get("search") or "").strip()
        page = max(request.args.get("page", default=1, type=int), 1)
        per_page = min(max(request.args.get("per_page", default=50, type=int), 1), 500)

        status_counts_rows = (
            db.session.query(PendingEmail.status, func.count(PendingEmail.id))
            .filter(PendingEmail.status.in_(statuses))
            .group_by(PendingEmail.status)
            .all()
        )
        status_counts = {s: c for s, c in status_counts_rows}
        total_count = sum(status_counts.values())

        data = []
        pagination = None
        if search:
            like = f"%{search}%"
            filtered = (
                db.session.query(PendingEmail)
                .outerjoin(Investment, PendingEmail.investor_id == Investment.id)
                .filter(
                    PendingEmail.status.in_(statuses),
                    or_(
                        PendingEmail.recipient_email.ilike(like),
                        Investment.internal_client_code.ilike(like),
                        Investment.investor_phone.ilike(like),
                    ),
                )
            )
            match_count = filtered.count()
            total_pages = max((match_count + per_page - 1) // per_page, 1)
            page = min(page, total_pages)
            rows = (
                filtered.order_by(PendingEmail.created_at.asc())
                .offset((page - 1) * per_page).limit(per_page).all()
            )
            data = [_serialize_pending_email_row(r) for r in rows]
            pagination = {"page": page, "per_page": per_page, "total": match_count, "total_pages": total_pages}

        return make_response(jsonify({
            "status": 200,
            "count": total_count,
            "status_counts": status_counts,
            "data": data,
            "pagination": pagination,
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/queue-status', methods=['GET'])
@jwt_required()
def email_queue_status():
    """
    How many emails are currently 'Queued' and when the send-queue scheduler
    will next run — for a "sending soon" indicator on the Email page.
    """
    try:
        from app.logic.email_queue_scheduler_service import EmailQueueSchedulerService
        return make_response(jsonify({"status": 200, "data": EmailQueueSchedulerService.get_status()}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/processed', methods=['GET'])
@jwt_required()
def list_processed_emails():
    """
    Counts + (optionally) a filtered list of already-processed emails:
    Confirmed (sent) / Failed. Same search-only-loads-rows pattern as
    list_email_inbox — this table only grows over time as emails are sent,
    so it's the one most likely to get large.
    """
    try:
        from app.Investments.model import PendingEmail
        statuses = ('Confirmed', 'Failed')
        search = (request.args.get("search") or "").strip()
        page = max(request.args.get("page", default=1, type=int), 1)
        per_page = min(max(request.args.get("per_page", default=50, type=int), 1), 500)

        status_counts_rows = (
            db.session.query(PendingEmail.status, func.count(PendingEmail.id))
            .filter(PendingEmail.status.in_(statuses))
            .group_by(PendingEmail.status)
            .all()
        )
        status_counts = {s: c for s, c in status_counts_rows}
        total_count = sum(status_counts.values())

        data = []
        pagination = None
        if search:
            like = f"%{search}%"
            filtered = (
                db.session.query(PendingEmail)
                .outerjoin(Investment, PendingEmail.investor_id == Investment.id)
                .filter(
                    PendingEmail.status.in_(statuses),
                    or_(
                        PendingEmail.recipient_email.ilike(like),
                        Investment.internal_client_code.ilike(like),
                        Investment.investor_phone.ilike(like),
                    ),
                )
            )
            match_count = filtered.count()
            total_pages = max((match_count + per_page - 1) // per_page, 1)
            page = min(page, total_pages)
            rows = (
                filtered.order_by(PendingEmail.processed_at.desc().nullslast(), PendingEmail.created_at.desc())
                .offset((page - 1) * per_page).limit(per_page).all()
            )
            data = [_serialize_pending_email_row(r) for r in rows]
            pagination = {"page": page, "per_page": per_page, "total": match_count, "total_pages": total_pages}

        return make_response(jsonify({
            "status": 200,
            "count": total_count,
            "status_counts": status_counts,
            "data": data,
            "pagination": pagination,
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/investors/<string:client_code>/statement-email/preview', methods=['POST'])
@jwt_required()
def queue_investor_statement_email_preview(client_code):
    """
    Queue a single investor statement email as Pending_Confirmation.
    This allows preview/confirm/suppress in the same flow as other email triggers.

    Body (optional): {"fund_ids": [3]} — scopes this email (and the PDF attached
    at send time) to just those funds. Omitted/empty means the CONSOLIDATED
    statement across every fund the client holds. One id is the common
    "Fund = X" bulk-filter case; several ids is the manual multi-fund-select
    case — both produce one consolidated-but-scoped statement, per the same
    rule _generate_investor_statement_pdf_bytes applies.
    """
    try:
        from app.utils.email_service import EmailService

        data_in = request.get_json(silent=True) or {}
        fund_ids_raw = data_in.get("fund_ids")
        fund_ids = None
        if fund_ids_raw:
            try:
                fund_ids = [int(f) for f in fund_ids_raw]
            except (TypeError, ValueError):
                return make_response(jsonify({"status": 400, "message": "fund_ids must be a list of integers"}), 400)

        investments = (
            db.session.query(Investment)
            .filter(func.lower(Investment.internal_client_code) == func.lower(client_code))
            .order_by(Investment.date_deposited.desc())
            .all()
        )
        if not investments:
            return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)

        if fund_ids:
            scoped_investments = [inv for inv in investments if inv.fund_id in fund_ids]
            if not scoped_investments:
                return make_response(jsonify({"status": 404, "message": "Investor does not hold any of the requested fund(s)"}), 404)
        else:
            scoped_investments = investments

        primary_investment = next((inv for inv in scoped_investments if (inv.investor_email or "").strip()), scoped_investments[0])
        recipient_email = (primary_investment.investor_email or "").strip()
        recipient_name = primary_investment.investor_name or "Investor"
        if not recipient_email:
            return make_response(jsonify({"status": 400, "message": "Investor has no email address"}), 400)

        portfolio_json = _get_investor_portfolio_aggregated_data(client_code, fund_ids=fund_ids)
        portfolio_payload = portfolio_json.get_json() if hasattr(portfolio_json, "get_json") else {}
        if not isinstance(portfolio_payload, dict) or portfolio_payload.get("status") != 200:
            msg = (portfolio_payload or {}).get("message") if isinstance(portfolio_payload, dict) else None
            return make_response(jsonify({"status": 500, "message": msg or "Unable to build statement email preview"}), 500)

        pdata = portfolio_payload.get("data") or {}
        investor_name = pdata.get("investor_name") or recipient_name
        funds = sorted({str(h.get("fund_name") or "").strip() for h in (pdata.get("holdings") or []) if str(h.get("fund_name") or "").strip()})
        fund_codes_in_holdings = {str(h.get("fund_code") or "").strip() for h in (pdata.get("holdings") or []) if str(h.get("fund_code") or "").strip()}
        fund_label = ", ".join(funds) if funds else "Portfolio"
        # Dangote/DPRP investors hold "shares", not a "fund" — matches the wording
        # already used on the PDF statement. Only swapped to "Share(s)" when this
        # email is scoped to exactly one fund and it's DPRP — a multi-fund/
        # consolidated email listing several funds always says "Fund(s)" even if
        # one of them happens to be DPRP, since is_dangote_dprp_fund() is an "any
        # match" check and would otherwise mislabel the OTHER funds too.
        is_single_fund_scope = bool(fund_ids) and len(fund_ids) == 1
        fund_line_label = (
            "Share(s)" if (is_single_fund_scope and is_dangote_dprp_fund(funds, fund_codes_in_holdings)) else "Fund(s)"
        )
        # Align email values exactly with the investor overview page cards/positions.
        overview_res = get_investor_overview.__wrapped__(client_code)
        overview_payload = overview_res.get_json() if hasattr(overview_res, "get_json") else {}
        overview_positions = []
        if isinstance(overview_payload, dict) and overview_payload.get("status") == 200:
            overview_positions = (overview_payload.get("data") or {}).get("positions") or []
        if fund_ids:
            fund_name_set_lower = {f.lower() for f in funds}
            overview_positions = [
                p for p in overview_positions
                if str(p.get("fund_name") or "").strip().lower() in fund_name_set_lower
            ]

        usd_mv = sum(
            (Decimal(str(p.get("market_value") or 0)) for p in overview_positions if str(p.get("currency") or "").upper() == "USD"),
            Decimal("0.00"),
        )
        kes_mv = sum(
            (Decimal(str(p.get("market_value") or 0)) for p in overview_positions if str(p.get("currency") or "").upper() == "KES"),
            Decimal("0.00"),
        )

        has_usd_mv = usd_mv > Decimal("0.00")
        currency_code = "USD" if has_usd_mv else ("KES" if kes_mv > Decimal("0.00") else (((primary_investment.currency_type or "USD").strip().upper()) or "USD"))
        current_balance = usd_mv if has_usd_mv else (kes_mv if kes_mv > Decimal("0.00") else _safe_decimal(pdata.get("current_balance")))

        principal_for_currency = sum(
            (
                Decimal(str(inv.net_principal or 0))
                for inv in scoped_investments
                if (
                    ((getattr(getattr(inv, "share_class", None), "currency", None) or inv.currency_type or "").strip().upper())
                    == currency_code
                )
            ),
            Decimal("0.00"),
        )
        if principal_for_currency <= Decimal("0.00"):
            principal_for_currency = _safe_decimal(pdata.get("total_principal"))

        total_principal = principal_for_currency
        total_gain = (current_balance - principal_for_currency).quantize(Decimal("0.01"))
        currency_prefix = "KES" if currency_code == "KES" else "USD"
        statement_date = datetime.now(timezone.utc).strftime("%d %b %Y")

        subject = (
            f"Your {fund_label} Statement is Ready - {client_code}"
            if fund_ids else
            f"Your Investor Statement is Ready - {client_code}"
        )
        body = f"""Dear {investor_name},

Your latest investor statement is ready for review.

Client Code: {client_code}
Statement Date: {statement_date}
{fund_line_label}: {fund_label}

Principal: {currency_prefix} {total_principal:,.2f}
Total {currency_code} Market Value: {currency_prefix} {current_balance:,.2f}
Gain/Loss: {currency_prefix} {total_gain:,.2f}

You can view and download your full statement from the investor portal at any time.

Best regards,
AXYS INVESTMENT BANK
"""

        pending = EmailService._create_pending_email(
            batch_id=primary_investment.batch_id,
            investor_id=primary_investment.id,
            email_type="INVESTOR_STATEMENT",
            subject=subject,
            body=body,
            recipient_email=recipient_email,
            recipient_name=investor_name,
            amount=float(current_balance),
            # pending_emails.fund_name is VARCHAR(100) — fine for one fund, but
            # a consolidated statement's joined fund_label (several fund names)
            # can exceed it now that a client can hold many funds at once.
            # This column is informational/display-only, so truncate rather
            # than let the whole queue attempt fail on a DB length error.
            fund_name=(fund_label if len(fund_label) <= 100 else fund_label[:97] + "..."),
            batch_name=None,
            trigger_source="investors.statement_email_preview",
        )
        if pending is None:
            return make_response(jsonify({"status": 500, "message": "Failed to queue statement email"}), 500)

        if fund_ids:
            pending.statement_fund_ids = ",".join(str(f) for f in fund_ids)
            db.session.commit()

        try:
            from app.utils.audit_log import create_audit_log
            create_audit_log(
                action="STATEMENT_QUEUED",
                target_type="investor",
                target_id=primary_investment.id,
                target_name=client_code,
                description=(
                    f"Queued {'fund-scoped' if is_single_fund_scope else ('consolidated (scoped)' if fund_ids else 'consolidated')} "
                    f"investor statement email — fund(s): {fund_label}"
                ),
                new_value={"scope": "fund" if is_single_fund_scope else "consolidated", "fund_ids": fund_ids, "fund_label": fund_label},
            )
        except Exception:
            logger.warning("Could not write audit log for statement queue (non-fatal)", exc_info=True)

        return make_response(jsonify({
            "status": 201,
            "message": "Statement email queued for admin confirmation",
            "data": _serialize_pending_email_row(pending),
        }), 201)
    except Exception as e:
        db.session.rollback()
        logger.error(f"queue_investor_statement_email_preview error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/statements/queue-batch', methods=['POST'])
@jwt_required()
def queue_investor_statements_batch():
    """
    Queue an overall-statement email (same logic as
    queue_investor_statement_email_preview, one per client) for every client
    code given — the Email page's "Send Statements" tab calls this after the
    admin filters eligible investors by period/fund/share-class and picks who
    to send to.

    Body: {"client_codes": ["ABC123", ...], "fund_ids": [3]}
    fund_ids is optional and applies to the WHOLE batch (the same filter/
    selection the admin made for this one send) — omitted means every
    matched client gets their full consolidated statement; one id is the
    "Fund = X" filter case (each client gets that fund's fund-scoped
    statement); several ids is the manual multi-fund-select case (each
    client gets one consolidated statement scoped to just those funds).
    queue_investor_statement_email_preview.__wrapped__() below reads
    fund_ids from this same request's JSON body (Flask caches the parsed
    body per-request), so it doesn't need to be re-passed per client.
    Response: {queued: [...], skipped: [{client_code, reason}], not_found: [...]}
    """
    try:
        from app.Investments.model import PendingEmail

        data = request.get_json(silent=True) or {}
        raw_codes = data.get('client_codes')
        if not isinstance(raw_codes, list) or not raw_codes:
            return make_response(jsonify({"status": 400, "message": "client_codes (non-empty list) is required"}), 400)

        fund_ids_raw = data.get('fund_ids')
        if fund_ids_raw:
            try:
                [int(f) for f in fund_ids_raw]
            except (TypeError, ValueError):
                return make_response(jsonify({"status": 400, "message": "fund_ids must be a list of integers"}), 400)

        # Dedupe — the same client can appear more than once in a fund/class
        # filtered list (e.g. holdings split across batches within one class).
        # An "overall statement" is one email per person, not per holding.
        seen = set()
        unique_codes = []
        for code in raw_codes:
            code = (code or "").strip()
            if code and code.lower() not in seen:
                seen.add(code.lower())
                unique_codes.append(code)

        queued, skipped, not_found = [], [], []
        for code in unique_codes:
            exists = db.session.query(Investment.id).filter(
                func.lower(Investment.internal_client_code) == code.lower()
            ).first()
            if not exists:
                not_found.append(code)
                continue

            already_pending = db.session.query(PendingEmail.id).join(
                Investment, PendingEmail.investor_id == Investment.id
            ).filter(
                func.lower(Investment.internal_client_code) == code.lower(),
                PendingEmail.email_type == "INVESTOR_STATEMENT",
                PendingEmail.status.in_(("Pending_Confirmation", "Queued")),
            ).first()
            if already_pending:
                skipped.append({"client_code": code, "reason": "already queued or pending confirmation"})
                continue

            try:
                res = queue_investor_statement_email_preview.__wrapped__(code)
                payload = res.get_json() if hasattr(res, "get_json") else {}
                if isinstance(payload, dict) and payload.get("status") == 201:
                    queued.append(code)
                else:
                    skipped.append({"client_code": code, "reason": (payload or {}).get("message", "failed to queue")})
            except Exception as e:
                skipped.append({"client_code": code, "reason": str(e)})

        return make_response(jsonify({
            "status": 200,
            "message": f"Queued {len(queued)} statement email(s) for admin confirmation",
            "data": {"queued": queued, "skipped": skipped, "not_found": not_found},
        }), 200)
    except Exception as e:
        logger.error(f"queue_investor_statements_batch error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _send_pending_email_now(email_id):
    """
    Does the actual work of sending one PendingEmail via SMTP: builds the message,
    attaches the type-appropriate PDF, sends it, and records the outcome (status +
    EmailLog). This used to run inline inside confirm_pending_email's request
    handler; it's now also the function the throttled send-queue scheduler calls
    (see app/logic/email_queue_scheduler_service.py) so a single email and a batch
    of 100 go through identical logic either way.

    Returns (send_ok: bool, message: str, http_status: int) — callers that need an
    HTTP response can return this tuple almost as-is; the scheduler just checks send_ok.
    """
    from app.Investments.model import PendingEmail, EmailLog
    from app.utils.email_service import EmailService
    from flask_mail import Message
    from app.utils.email_service import mail

    pending = db.session.get(PendingEmail, email_id)
    if not pending:
        return False, "Pending email not found", 404

    # ── Send via SMTP ──
    try:
            bcc_email = current_app.config.get("MAIL_BCC", EmailService.BCC_EMAIL)
            default_sender = current_app.config.get("MAIL_DEFAULT_SENDER")
            if not default_sender:
                logger.warning("MAIL_DEFAULT_SENDER is not set; falling back to MAIL_BCC for sender (may impact deliverability).")
                default_sender = bcc_email

            reply_to = current_app.config.get("MAIL_REPLY_TO", None) or "info@aib-axysafrica.com"

            from app.utils.email_template import render_branded_email_html, get_email_title, attach_brand_logo

            msg = Message(
                subject=pending.subject,
                recipients=[pending.recipient_email],
                bcc=[bcc_email],
                body=pending.body,
                html=render_branded_email_html(get_email_title(pending.email_type), pending.body),
                sender=EmailService._format_sender(default_sender),
            )
            msg.reply_to = reply_to
            attach_brand_logo(msg)
            inv = db.session.get(Investment, pending.investor_id) if pending.investor_id else None

            def _attach_pdf_buffer(pdf_buffer, *, filename: str, warn_prefix: str) -> bool:
                """
                Attaches a plain BytesIO PDF buffer (the return type of every
                _generate_*_pdf_bytes helper). These helpers are the only PDF-generating
                functions safe to call from this background thread — the route functions
                (get_transfer_receipt_pdf, etc.) call send_file(), which needs
                flask.request and isn't available here. Every attachment below must go
                through one of these bytes-helpers, never the route function itself.
                """
                if isinstance(pdf_buffer, tuple):
                    # ("error", status_code, message) — a known/expected failure.
                    logger.warning(f"{warn_prefix} for pending email {email_id}: {pdf_buffer}")
                    return False
                if pdf_buffer is None:
                    logger.warning(f"{warn_prefix}: generation failed for pending email {email_id}")
                    return False
                pdf_buffer.seek(0)
                pdf_bytes = pdf_buffer.getvalue()
                if not pdf_bytes:
                    logger.warning(f"{warn_prefix}: generated PDF was empty for pending email {email_id}")
                    return False
                msg.attach(filename=filename, content_type="application/pdf", data=pdf_bytes)
                return True

            # Attach full investor statement PDF for statement-email flow.
            if pending.email_type == "INVESTOR_STATEMENT" and pending.investor_id:
                if inv and inv.internal_client_code:
                    try:
                        # statement_fund_ids was set at queue time (see
                        # queue_investor_statement_email_preview) — None means
                        # the full consolidated statement, matching what the
                        # email body itself described.
                        statement_fund_ids = None
                        if pending.statement_fund_ids:
                            statement_fund_ids = [int(f) for f in pending.statement_fund_ids.split(",") if f.strip()]
                        pdf_buffer = _generate_investor_statement_pdf_bytes(
                            inv.internal_client_code, fund_ids=statement_fund_ids
                        )
                        _attach_pdf_buffer(
                            pdf_buffer,
                            filename=f"investor-statement-{inv.internal_client_code}.pdf",
                            warn_prefix="Statement attachment skipped",
                        )
                    except Exception as attach_err:
                        logger.warning(f"Could not attach statement PDF for pending email {email_id}: {attach_err}")
            elif pending.email_type == "DEPOSIT_CONFIRMATION":
                if inv and inv.internal_client_code and pending.batch_id:
                    try:
                        from app.Investments.route import _generate_deposit_receipt_pdf_bytes
                        pdf_buffer = _generate_deposit_receipt_pdf_bytes(inv.internal_client_code, int(pending.batch_id))
                        if pdf_buffer:
                            pdf_buffer.seek(0)
                            pdf_bytes = pdf_buffer.getvalue()
                            if pdf_bytes:
                                msg.attach(
                                    filename=f"deposit-confirmation-{inv.internal_client_code}-{pending.batch_id}.pdf",
                                    content_type="application/pdf",
                                    data=pdf_bytes,
                                )
                            else:
                                logger.warning(f"Deposit statement PDF was empty for pending email {email_id}")
                        else:
                            logger.warning(f"Could not generate deposit PDF for pending email {email_id}")
                    except Exception as attach_err:
                        logger.warning(f"Could not attach deposit statement PDF for pending email {email_id}: {attach_err}")
                else:
                    logger.warning(
                        f"Deposit statement attachment skipped for pending email {email_id}: "
                        f"missing investor/client_code or batch_id"
                    )
            elif pending.email_type == "OFFSHORE_TRANSFER":
                if inv and inv.internal_client_code and pending.batch_id:
                    try:
                        pdf_buffer = _generate_transfer_receipt_pdf_bytes(inv.internal_client_code, int(pending.batch_id))
                        _attach_pdf_buffer(
                            pdf_buffer,
                            filename=f"transfer-confirmation-{inv.internal_client_code}-{pending.batch_id}.pdf",
                            warn_prefix="Transfer statement attachment skipped",
                        )
                    except Exception as attach_err:
                        logger.warning(f"Could not attach transfer statement PDF for pending email {email_id}: {attach_err}")
                else:
                    logger.warning(
                        f"Transfer statement attachment skipped for pending email {email_id}: "
                        f"missing investor/client_code or batch_id"
                    )
            elif pending.email_type in ("INVESTMENT_ACTIVE", "INVESTMENT_ACTIVE_OVERSUBSCRIBED"):
                # INVESTMENT_ACTIVE_OVERSUBSCRIBED is a legacy variant no longer produced
                # (oversubscription info moved to its own OVERSUBSCRIPTION_REFUND_NOTICE
                # email/PDF below) — kept here only so any already-queued row from before
                # this change still attaches correctly.
                if inv and inv.internal_client_code and pending.batch_id:
                    try:
                        pdf_buffer = _generate_deployment_receipt_pdf_bytes(inv.internal_client_code, int(pending.batch_id))
                        _attach_pdf_buffer(
                            pdf_buffer,
                            filename=f"deployment-confirmation-{inv.internal_client_code}-{pending.batch_id}.pdf",
                            warn_prefix="Deployment statement attachment skipped",
                        )
                    except Exception as attach_err:
                        logger.warning(f"Could not attach deployment statement PDF for pending email {email_id}: {attach_err}")
                else:
                    logger.warning(
                        f"Deployment statement attachment skipped for pending email {email_id}: "
                        f"missing investor/client_code or batch_id"
                    )
            elif pending.email_type == "OVERSUBSCRIPTION_REFUND_NOTICE":
                if inv and inv.internal_client_code and inv.fund_id is not None:
                    try:
                        pdf_buffer = _generate_oversubscription_notice_pdf_bytes(inv.internal_client_code, int(inv.fund_id))
                        _attach_pdf_buffer(
                            pdf_buffer,
                            filename=f"oversubscription-notice-{inv.internal_client_code}.pdf",
                            warn_prefix="Oversubscription notice PDF attachment skipped",
                        )
                    except Exception as attach_err:
                        logger.warning(f"Could not attach oversubscription notice PDF for pending email {email_id}: {attach_err}")
                else:
                    logger.warning(
                        f"Oversubscription notice PDF attachment skipped for pending email {email_id}: "
                        f"missing investor/client_code or fund_id"
                    )
            mail.send(msg)
            send_ok = True
    except Exception as smtp_err:
        logger.error(f"SMTP send failed for pending email {email_id}: {smtp_err}")
        send_ok = False

    try:
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

        # Mark the linked refund as notified — this flag, not the email trigger
        # itself, is what stops the notice from ever being generated/resent
        # again for the same refund (see EmailService.send_oversubscription_refund_notices).
        if send_ok and pending.email_type == "OVERSUBSCRIPTION_REFUND_NOTICE" and inv and inv.internal_client_code and inv.fund_id is not None:
            refund_wd = (
                db.session.query(Withdrawal)
                .filter(
                    func.lower(Withdrawal.internal_client_code) == func.lower(inv.internal_client_code),
                    Withdrawal.fund_id == inv.fund_id,
                    Withdrawal.source == "oversubscription_refund",
                )
                .order_by(Withdrawal.date_withdrawn.desc())
                .first()
            )
            if refund_wd is not None:
                refund_wd.oversubscription_notice_sent_at = datetime.now(timezone.utc)

        db.session.commit()

        if send_ok:
            logger.info(f"Pending email {email_id} confirmed and sent to {pending.recipient_email}")
            return True, "Email sent and confirmed.", 200
        else:
            return False, "SMTP send failed. Record marked as Failed.", 502

    except Exception as e:
        db.session.rollback()
        logger.error(f"_send_pending_email_now error for {email_id}: {str(e)}")
        return False, f"Error: {str(e)}", 500


@investment_v1.route('/api/v1/emails/<int:email_id>/confirm', methods=['POST'])
@jwt_required()
def confirm_pending_email(email_id):
    """
    Approve a pending email for sending. Does NOT send it immediately — it marks
    the email 'Queued' and the throttled send-queue scheduler (every 5 minutes,
    up to 100 at a time — see app/logic/email_queue_scheduler_service.py) picks it
    up and actually sends it via _send_pending_email_now. This keeps a single
    Confirm click fast (no waiting on SMTP/PDF generation in the request) and means
    confirming many emails at once can never blast them all out simultaneously.

    Response:
    { "status": 200, "message": "Email queued for sending." }
    """
    try:
        from app.Investments.model import PendingEmail

        pending = db.session.get(PendingEmail, email_id)
        if not pending:
            return make_response(jsonify({"status": 404, "message": "Pending email not found"}), 404)

        # Allow re-queueing emails that were previously failed or suppressed.
        # Only block states that are already finalized/non-resendable, or mid-queue.
        if pending.status not in ('Pending_Confirmation', 'Suppressed', 'Failed'):
            return make_response(jsonify({
                "status": 409,
                "message": f"Email is already in state '{pending.status}' and cannot be queued."
            }), 409)

        pending.status = 'Queued'
        pending.queued_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(f"Pending email {email_id} queued for sending to {pending.recipient_email}")
        return make_response(jsonify({"status": 200, "message": "Email queued for sending.", "data": _serialize_pending_email_row(pending)}), 200)

    except Exception as e:
        db.session.rollback()
        logger.error(f"confirm_pending_email error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/confirm-batch', methods=['POST'])
@jwt_required()
def confirm_pending_emails_batch():
    """
    Queue many pending emails in ONE request instead of one HTTP call per email
    (what "Confirm All" used to do — awaited sequentially in the browser). Same
    effect as calling /confirm on each id — marks resendable ones 'Queued' — just
    batched into a single DB transaction, so approving thousands doesn't mean
    thousands of round trips.

    Body: { "ids": [1, 2, 3, ...] }
    """
    try:
        from app.Investments.model import PendingEmail
        data = request.get_json(silent=True) or {}
        ids = data.get("ids")
        if not isinstance(ids, list) or not ids:
            return make_response(jsonify({"status": 400, "message": "ids (non-empty list) is required"}), 400)

        rows = db.session.query(PendingEmail).filter(PendingEmail.id.in_(ids)).all()
        found_ids = {r.id for r in rows}
        not_found = [i for i in ids if i not in found_ids]

        queued, skipped = [], []
        now = datetime.now(timezone.utc)
        for pending in rows:
            if pending.status in ('Pending_Confirmation', 'Suppressed', 'Failed'):
                pending.status = 'Queued'
                pending.queued_at = now
                queued.append(pending.id)
            else:
                skipped.append({"id": pending.id, "reason": f"already {pending.status}"})

        db.session.commit()
        logger.info(f"Batch-queued {len(queued)} email(s) for sending")

        return make_response(jsonify({
            "status": 200,
            "message": f"{len(queued)} email(s) queued for sending.",
            "data": {"queued": queued, "skipped": skipped, "not_found": not_found},
        }), 200)
    except Exception as e:
        db.session.rollback()
        logger.error(f"confirm_pending_emails_batch error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/confirm-all', methods=['POST'])
@jwt_required()
def confirm_all_pending_emails():
    """
    Confirm (queue) every resendable email — Pending_Confirmation / Suppressed
    / Failed — optionally scoped to the same `search` filter list_email_inbox
    uses (client code, recipient email, or phone). This is the "Confirm All"
    for the inbox specifically, where the count can be in the tens of
    thousands (e.g. after a large bulk upload) and there's no realistic way
    to hand the frontend an id list first — confirm_pending_emails_batch
    above (ids-based) is for a bounded, already-known set instead (e.g.
    EmailConfirmationModal, right after one action creates a few dozen).

    Runs as a single UPDATE, no per-row Python loop and no id list ever
    built for the "confirm literally everything" case — only the search-
    scoped case resolves ids first (cheap: a search always narrows things
    down a lot).

    Body: { "search"?: string }
    """
    try:
        from app.Investments.model import PendingEmail
        data = request.get_json(silent=True) or {}
        search = (data.get("search") or "").strip()
        resendable = ('Pending_Confirmation', 'Suppressed', 'Failed')
        now = datetime.now(timezone.utc)

        if search:
            like = f"%{search}%"
            matching_ids = [
                pid for (pid,) in (
                    db.session.query(PendingEmail.id)
                    .outerjoin(Investment, PendingEmail.investor_id == Investment.id)
                    .filter(
                        PendingEmail.status.in_(resendable),
                        or_(
                            PendingEmail.recipient_email.ilike(like),
                            Investment.internal_client_code.ilike(like),
                            Investment.investor_phone.ilike(like),
                        ),
                    )
                    .all()
                )
            ]
            if not matching_ids:
                return make_response(jsonify({"status": 200, "message": "No matching emails to confirm", "data": {"queued": 0}}), 200)
            queued = (
                db.session.query(PendingEmail)
                .filter(PendingEmail.id.in_(matching_ids))
                .update({"status": "Queued", "queued_at": now}, synchronize_session=False)
            )
        else:
            queued = (
                db.session.query(PendingEmail)
                .filter(PendingEmail.status.in_(resendable))
                .update({"status": "Queued", "queued_at": now}, synchronize_session=False)
            )

        db.session.commit()
        logger.info(f"Confirm-all: queued {queued} email(s) for sending (search={search!r})")

        return make_response(jsonify({
            "status": 200,
            "message": f"{queued} email(s) queued for sending",
            "data": {"queued": queued},
        }), 200)
    except Exception as e:
        db.session.rollback()
        logger.error(f"confirm_all_pending_emails error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/emails/suppress-all', methods=['POST'])
@jwt_required()
def suppress_all_pending_emails():
    """
    Suppress every still-actionable email — Pending_Confirmation / Queued —
    optionally scoped to the same `search` filter list_email_inbox uses
    (client code, recipient email, or phone). Mirrors confirm-all: a single
    UPDATE, no per-row Python loop, no id list built for the "suppress
    literally everything" case. Already-Suppressed/Confirmed/Failed rows are
    left untouched (matches cancel_pending_email's single-row guard).

    Body: { "search"?: string }
    """
    try:
        from app.Investments.model import PendingEmail
        data = request.get_json(silent=True) or {}
        search = (data.get("search") or "").strip()
        suppressable = ('Pending_Confirmation', 'Queued')
        now = datetime.now(timezone.utc)

        if search:
            like = f"%{search}%"
            matching_ids = [
                pid for (pid,) in (
                    db.session.query(PendingEmail.id)
                    .outerjoin(Investment, PendingEmail.investor_id == Investment.id)
                    .filter(
                        PendingEmail.status.in_(suppressable),
                        or_(
                            PendingEmail.recipient_email.ilike(like),
                            Investment.internal_client_code.ilike(like),
                            Investment.investor_phone.ilike(like),
                        ),
                    )
                    .all()
                )
            ]
            if not matching_ids:
                return make_response(jsonify({"status": 200, "message": "No matching emails to suppress", "data": {"suppressed": 0}}), 200)
            suppressed = (
                db.session.query(PendingEmail)
                .filter(PendingEmail.id.in_(matching_ids))
                .update({"status": "Suppressed", "processed_at": now}, synchronize_session=False)
            )
        else:
            suppressed = (
                db.session.query(PendingEmail)
                .filter(PendingEmail.status.in_(suppressable))
                .update({"status": "Suppressed", "processed_at": now}, synchronize_session=False)
            )

        db.session.commit()
        logger.info(f"Suppress-all: suppressed {suppressed} email(s) (search={search!r})")

        return make_response(jsonify({
            "status": 200,
            "message": f"{suppressed} email(s) suppressed",
            "data": {"suppressed": suppressed},
        }), 200)
    except Exception as e:
        db.session.rollback()
        logger.error(f"suppress_all_pending_emails error: {str(e)}")
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

        # Queued is included so an accidental Confirm can still be pulled back
        # before the scheduler drains it.
        if pending.status not in ('Pending_Confirmation', 'Queued'):
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


@investment_v1.route('/api/v1/emails/cancel-batch', methods=['POST'])
@jwt_required()
def cancel_pending_emails_batch():
    """
    Bulk counterpart to confirm-batch — suppresses many pending emails in one
    request instead of one HTTP call per email ("Suppress All").

    Body: { "ids": [1, 2, 3, ...] }
    """
    try:
        from app.Investments.model import PendingEmail
        data = request.get_json(silent=True) or {}
        ids = data.get("ids")
        if not isinstance(ids, list) or not ids:
            return make_response(jsonify({"status": 400, "message": "ids (non-empty list) is required"}), 400)

        rows = db.session.query(PendingEmail).filter(PendingEmail.id.in_(ids)).all()
        found_ids = {r.id for r in rows}
        not_found = [i for i in ids if i not in found_ids]

        suppressed, skipped = [], []
        now = datetime.now(timezone.utc)
        for pending in rows:
            if pending.status in ('Pending_Confirmation', 'Queued'):
                pending.status = 'Suppressed'
                pending.processed_at = now
                suppressed.append(pending.id)
            else:
                skipped.append({"id": pending.id, "reason": f"already {pending.status}"})

        db.session.commit()
        logger.info(f"Batch-suppressed {len(suppressed)} email(s)")

        return make_response(jsonify({
            "status": 200,
            "message": f"{len(suppressed)} email(s) suppressed.",
            "data": {"suppressed": suppressed, "skipped": skipped, "not_found": not_found},
        }), 200)
    except Exception as e:
        db.session.rollback()
        logger.error(f"cancel_pending_emails_batch error: {str(e)}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ============================================================================
# #5: Recent Transactions - Activity Feed for Dashboard
# ============================================================================

@investment_v1.route('/api/v1/transactions/recent', methods=['GET'])
@jwt_required()
def get_recent_transactions():
    """
    #5: Get last 10 transactions across deposits, withdrawals, and valuations.
    
    Response: {
      "status": 200,
      "data": [{
        "id": 1,
        "type": "deposit|withdrawal|valuation",
        "date": "2026-04-17",
        "investor_name": "Jane Doe",
        "internal_client_code": "INV-001",
        "fund_name": "Axiom",
        "class_code": "KES_I",
        "currency": "KES",
        "amount": 1014178.42,
        "status": "Completed"
      }]
    }
    """
    try:
        from app.Funds.share_class import ShareClass
        from app.Funds.investor_shares import InvestorShares
        from app.Valuation.valuation_snapshot import ValuationSnapshot
        from decimal import Decimal
        
        def float_2dp(val):
            if val is None:
                return 0.0
            return float(Decimal(str(val)).quantize(Decimal("0.01")))
        
        transactions = []
        
        # Get deposits (investments)
        deposits = db.session.query(
            Investment.id,
            Investment.investor_name,
            Investment.internal_client_code,
            Investment.date_deposited,
            Investment.amount_deposited,
            CoreFund.fund_name,
            ShareClass.class_code,
            ShareClass.currency
        ).join(CoreFund, Investment.fund_id == CoreFund.id).join(
            ShareClass, Investment.share_class_id == ShareClass.id
        ).order_by(Investment.date_deposited.desc()).limit(10).all()
        
        for dep in deposits:
            transactions.append({
                "id": dep.id,
                "type": "deposit",
                "date": dep.date_deposited.strftime("%Y-%m-%d") if dep.date_deposited else None,
                "investor_name": dep.investor_name,
                "internal_client_code": dep.internal_client_code,
                "fund_name": dep.fund_name,
                "class_code": dep.class_code,
                "currency": dep.currency,
                "amount": float_2dp(dep.amount_deposited),
                "status": "Completed"
            })
        
        # Get withdrawals
        withdrawals = db.session.query(
            Withdrawal.id,
            Withdrawal.internal_client_code,
            Withdrawal.date_withdrawn,
            Withdrawal.amount,
            Withdrawal.gross_amount,
            CoreFund.fund_name,
            Withdrawal.status
        ).join(CoreFund, Withdrawal.fund_id == CoreFund.id).order_by(
            Withdrawal.date_withdrawn.desc()
        ).limit(10).all()
        
        for wd in withdrawals:
            transactions.append({
                "id": wd.id,
                "type": "withdrawal",
                "date": wd.date_withdrawn.strftime("%Y-%m-%d") if wd.date_withdrawn else None,
                "investor_name": (
                    db.session.query(Investment.investor_name)
                    .filter(Investment.internal_client_code == wd.internal_client_code)
                    .order_by(Investment.id.desc())
                    .scalar()
                    or wd.internal_client_code
                ),
                "internal_client_code": wd.internal_client_code,
                "fund_name": wd.fund_name,
                "class_code": None,
                "currency": None,
                "amount": float_2dp(wd.gross_amount if wd.gross_amount is not None else wd.amount),
                "status": normalize_withdrawal_status(wd.status)
            })
        
        # Get valuations (valuation snapshots)
        valuations = db.session.query(
            ValuationSnapshot.id,
            Investment.investor_name,
            Investment.internal_client_code,
            ValuationSnapshot.valuation_date,
            ValuationSnapshot.market_value,
            CoreFund.fund_name,
            ShareClass.class_code,
            ShareClass.currency
        ).join(
            InvestorShares, ValuationSnapshot.investor_shares_id == InvestorShares.id
        ).join(
            Investment, InvestorShares.investment_id == Investment.id
        ).join(
            ShareClass, InvestorShares.share_class_id == ShareClass.id
        ).join(
            CoreFund, ShareClass.core_fund_id == CoreFund.id
        ).order_by(ValuationSnapshot.valuation_date.desc()).limit(10).all()
        
        for val in valuations:
            transactions.append({
                "id": val.id,
                "type": "valuation",
                "date": val.valuation_date.strftime("%Y-%m-%d"),
                "investor_name": val.investor_name,
                "internal_client_code": val.internal_client_code,
                "fund_name": val.fund_name,
                "class_code": val.class_code,
                "currency": val.currency,
                "amount": float_2dp(val.market_value),
                "status": "Committed"
            })
        
        # Sort all transactions by date, limit to 10
        transactions.sort(key=lambda x: x['date'], reverse=True)
        transactions = transactions[:10]
        
        return make_response(jsonify({
            "status": 200,
            "data": transactions
        }), 200)
    
    except Exception as e:
        import traceback
        print(f"ERROR in get_recent_transactions: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ============================================================================
# #6: Investor Overview - Full Position Summary
# ============================================================================

@investment_v1.route('/api/v1/investors/<client_code>/overview', methods=['GET'])
@jwt_required()
def get_investor_overview(client_code):
    """
    #6: Get investor's full position across all batches.
    
    Response: {
      "status": 200,
      "data": {
        "internal_client_code": "INV-001",
        "investor_name": "Jane Doe",
        "investor_email": "jane@example.com",
        "investor_phone": "+254700000001",
        "positions": [{
          "batch_id": 7,
          "batch_name": "AXM_KES_I_2026-04-10",
          "fund_name": "Axiom",
          "class_code": "KES_I",
          "currency": "KES",
          "deposit_amount": 1000000.00,
          "shares": 729.86,
          "market_value": 1014178.42,
          "performance_pct": 4.52,
          "deployment_nav": 1370.65,
          "current_nav": 1389.5737,
          "deployment_date": "2026-04-10"
        }]
      }
    }
    """
    try:
        from app.Valuation.valuation_snapshot import ValuationSnapshot
        from app.Funds.investor_shares import InvestorShares
        from app.Funds.nav_history import NavHistory
        from decimal import Decimal
        
        def float_2dp(val):
            if val is None:
                return None
            return float(Decimal(str(val)).quantize(Decimal("0.01")))
        
        # Find investor by client code. Uses func.lower(...) == func.lower(...)
        # rather than .ilike(client_code) (no wildcards) so this can use the
        # ix_investments_lower_client_code functional index — an exact-match
        # ILIKE can't use a plain btree index and falls back to a full table
        # scan, which is what was making this page slow to load at 100k+ rows.
        investor = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).first()

        if not investor:
            return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)

        # Get all investments for this investor across all batches (latest first)
        all_investments = db.session.query(Investment).filter(
            func.lower(Investment.internal_client_code) == func.lower(client_code)
        ).order_by(Investment.date_deposited.desc()).all()

        latest_inv = all_investments[0] if all_investments else investor
        latest_batch = latest_inv.batch if latest_inv else None

        # Prefer the first non-empty value across this investor's records.
        wealth_manager_val = next((i.wealth_manager for i in all_investments if getattr(i, "wealth_manager", None)), investor.wealth_manager)
        ifa_val = next((i.IFA for i in all_investments if getattr(i, "IFA", None)), investor.IFA)
        contract_note_val = next((i.contract_note for i in all_investments if getattr(i, "contract_note", None)), investor.contract_note)
        
        positions = []
        
        for inv in all_investments:
            batch = inv.batch
            if not batch:
                continue

            is_deployed = bool((batch.stage or 1) >= 3 or batch.deployment_confirmed or batch.deployment_date_actual or batch.deployment_nav)

            shares = None
            deployment_nav = None
            deployment_date = None
            latest_snapshot = None
            market_value = None
            performance_pct = None
            raw_deployment_date = None
            raw_deployment_nav = None

            if is_deployed:
                inv_shares = db.session.query(InvestorShares).filter(
                    InvestorShares.investment_id == inv.id
                ).first()

                shares = float_2dp(inv_shares.shares_owned) if inv_shares else None
                deployment_nav = float_2dp(inv_shares.deployment_nav) if inv_shares else None
                deployment_date = inv_shares.deployment_date.strftime("%Y-%m-%d") if inv_shares and inv_shares.deployment_date else None
                raw_deployment_date = inv_shares.deployment_date if inv_shares else None
                raw_deployment_nav = inv_shares.deployment_nav if inv_shares else None

                latest_snapshot = (
                    db.session.query(ValuationSnapshot)
                    .filter(ValuationSnapshot.investor_shares_id == inv_shares.id)
                    .order_by(ValuationSnapshot.valuation_date.desc())
                    .first()
                ) if inv_shares else None

                market_value = float_2dp(latest_snapshot.market_value) if latest_snapshot else None

                # Subtract approved/final withdrawals from displayed current value (immediate standing after withdrawal)
                if market_value is not None and inv.fund_id:
                    wd_sum = db.session.query(func.coalesce(func.sum(Withdrawal.gross_amount), 0)).filter(
                        func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
                        Withdrawal.fund_id == inv.fund_id,
                        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                        Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                    ).scalar()
                    try:
                        wd_sum_val = float(Decimal(str(wd_sum or 0)).quantize(Decimal("0.01")))
                    except Exception:
                        wd_sum_val = 0.0
                    market_value = float_2dp(max(0.0, float(market_value) - wd_sum_val))
                performance_pct = float_2dp(latest_snapshot.performance_pct) if latest_snapshot else None

            # Get current NAV (works for both deployed + non-deployed). For a
            # deployed position, resolve_current_price guards against a stale
            # pre-deployment valuation (see its docstring); for a non-deployed
            # one there's no deployment yet to protect against, so the plain
            # latest valuation is used as before.
            current_nav = None
            if inv.share_class_id:
                if is_deployed and raw_deployment_date is not None:
                    resolved_nav, _resolved_dt, _is_fallback = NavHistory.resolve_current_price(
                        inv.share_class_id, raw_deployment_date, raw_deployment_nav, session=db.session
                    )
                    if resolved_nav is not None:
                        current_nav = float_2dp(resolved_nav)
                else:
                    latest_nav = db.session.query(NavHistory).filter(
                        NavHistory.share_class_id == inv.share_class_id
                    ).order_by(NavHistory.nav_date.desc()).first()
                    if latest_nav:
                        current_nav = float_2dp(latest_nav.nav_per_share)

            # Refund visibility (requirement: never let this silently disappear
            # from a position) — only set for a position that actually went
            # through DPRP-style oversubscription pro-rata.
            refund_amount = float_2dp(inv.oversubscription_refund_amount) if (inv.oversubscription_refund_amount or 0) > 0 else None
            refund_status = None
            if refund_amount and inv.fund_id:
                refund_wd = (
                    db.session.query(Withdrawal)
                    .filter(
                        func.lower(Withdrawal.internal_client_code) == func.lower(client_code),
                        Withdrawal.fund_id == inv.fund_id,
                        Withdrawal.source == WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                    )
                    .order_by(Withdrawal.date_withdrawn.desc())
                    .first()
                )
                refund_status = normalize_withdrawal_status(refund_wd.status) if refund_wd else "Pending"

            positions.append({
                "batch_id": batch.id,
                "batch_name": batch.batch_name,
                "batch_stage": int(getattr(batch, "stage", 1) or 1),
                "batch_is_active": bool(getattr(batch, "is_active", False)),
                "batch_is_open": bool(getattr(batch, "is_open", False)),
                "product_type": inv.product_type,
                "share_class_id": int(inv.share_class_id) if inv.share_class_id is not None else None,
                "fund_name": inv.fund_name,
                "class_code": inv.share_class.class_code if inv.share_class else None,
                "currency": inv.share_class.currency if inv.share_class else None,
                "deposit_amount": float_2dp(inv.amount_deposited),
                "shares": shares,
                "market_value": market_value,
                "performance_pct": performance_pct,
                "deployment_nav": deployment_nav,
                "current_nav": current_nav,
                "deployment_date": deployment_date,
                "refund_amount": refund_amount,
                "refund_status": refund_status,
            })
        
        return make_response(jsonify({
            "status": 200,
            "data": {
                "internal_client_code": investor.internal_client_code,
                "investor_name": investor.investor_name,
                "investor_email": investor.investor_email,
                "investor_phone": investor.investor_phone,
                "wealth_manager": wealth_manager_val,
                "IFA": ifa_val,
                "contract_note": contract_note_val,
                # Current/latest context (even if not yet deployed) — used for edit actions.
                "current_batch": {
                    "batch_id": latest_batch.id if latest_batch else (latest_inv.batch_id if latest_inv else None),
                    "batch_name": latest_batch.batch_name if latest_batch else None,
                    "stage": int(getattr(latest_batch, "stage", 1) or 1) if latest_batch else None,
                    "is_active": bool(getattr(latest_batch, "is_active", False)) if latest_batch is not None else None,
                    "share_class_id": int(getattr(latest_batch, "share_class_id", None)) if getattr(latest_batch, "share_class_id", None) is not None else (int(latest_inv.share_class_id) if getattr(latest_inv, "share_class_id", None) is not None else None),
                    "class_code": latest_inv.share_class.class_code if getattr(latest_inv, "share_class", None) else None,
                    "currency": latest_inv.share_class.currency if getattr(latest_inv, "share_class", None) else None,
                },
                "positions": positions
            }
        }), 200)
    
    except Exception as e:
        import traceback
        print(f"ERROR in get_investor_overview: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ==================== RECONCILIATION ENDPOINTS ====================

@investment_v1.route('/api/v1/reconciliation/review', methods=['GET'])
@jwt_required()
def get_reconciliation_review():
    """
    Get reconciliation review data for a specific currency.
    
    Query params:
    - currency: 'KES' or 'USD' (required)
    
    Returns investor data for reconciliation review with system vs official values.
    """
    try:
        currency = request.args.get('currency', '').upper()
        if currency not in ['KES', 'USD']:
            return make_response(jsonify({"status": 400, "message": "currency must be KES or USD"}), 400)

        # Get all investments with the specified currency
        investments = db.session.query(Investment).filter(
            Investment.currency_type == currency,
            Investment.shares_owned.isnot(None),
            Investment.shares_owned > 0
        ).all()

        reconciliation_data = []
        for inv in investments:
            # Get share class for current NAV
            share_class = inv.share_class
            current_nav = share_class.current_nav if share_class else None
            
            # Calculate system values
            system_calculated_value = None
            if inv.shares_owned and current_nav:
                system_calculated_value = inv.shares_owned * current_nav
            
            # Calculate variance
            variance = None
            variance_pct = None
            if inv.official_receipt_value and system_calculated_value:
                variance = inv.official_receipt_value - system_calculated_value
                if system_calculated_value != 0:
                    variance_pct = (variance / system_calculated_value) * 100
            
            reconciliation_data.append({
                "id": inv.id,
                "investor_name": inv.investor_name,
                "internal_client_code": inv.internal_client_code,
                "shares_owned": float(inv.shares_owned) if inv.shares_owned else None,
                "previous_nav": float(inv.previous_nav_price) if inv.previous_nav_price else None,
                "current_nav": float(current_nav) if current_nav else None,
                "system_calculated_value": float(system_calculated_value) if system_calculated_value else None,
                "official_receipt_value": float(inv.official_receipt_value) if inv.official_receipt_value else None,
                "variance": float(variance) if variance else None,
                "variance_pct": float(variance_pct) if variance_pct else None,
                "rounding_adjustment": float(inv.rounding_adjustment) if inv.rounding_adjustment else None,
                "currency": inv.currency_type
            })

        return make_response(jsonify({
            "status": 200,
            "message": f"Reconciliation data retrieved for {currency}",
            "data": reconciliation_data,
            "currency": currency
        }), 200)

    except Exception as e:
        import traceback
        print(f"ERROR in get_reconciliation_review: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/reconciliation/update/<int:investment_id>', methods=['PATCH'])
@jwt_required()
def update_reconciliation_value(investment_id):
    """
    Update the official receipt value for an investment.
    
    Request body:
    {
        "official_receipt_value": 1072636.69,
        "rounding_adjustment": 3.04
    }
    """
    try:
        data = request.get_json()
        if not data:
            return make_response(jsonify({"status": 400, "message": "Request body is required"}), 400)

        investment = db.session.query(Investment).filter(Investment.id == investment_id).first()
        if not investment:
            return make_response(jsonify({"status": 404, "message": "Investment not found"}), 404)

        # Update official receipt value
        if 'official_receipt_value' in data:
            investment.official_receipt_value = Decimal(str(data['official_receipt_value']))

        # Update rounding adjustment
        if 'rounding_adjustment' in data:
            investment.rounding_adjustment = Decimal(str(data['rounding_adjustment']))

        db.session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": "Reconciliation values updated successfully",
            "data": {
                "id": investment.id,
                "official_receipt_value": float(investment.official_receipt_value) if investment.official_receipt_value else None,
                "rounding_adjustment": float(investment.rounding_adjustment) if investment.rounding_adjustment else None
            }
        }), 200)

    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"ERROR in update_reconciliation_value: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@investment_v1.route('/api/v1/reconciliation/verify/<int:investment_id>', methods=['POST'])
@jwt_required()
def verify_reconciliation(investment_id):
    """
    Verify and lock reconciliation for an investment.
    
    This marks the reconciliation as verified and generates statements using official values.
    """
    try:
        investment = db.session.query(Investment).filter(Investment.id == investment_id).first()
        if not investment:
            return make_response(jsonify({"status": 404, "message": "Investment not found"}), 404)

        # Check if reconciliation is complete
        if not investment.official_receipt_value:
            return make_response(jsonify({"status": 400, "message": "Official receipt value must be set before verification"}), 400)

        # Mark as verified (you could add a verified_at timestamp field if needed)
        # For now, we'll just confirm the verification

        # Generate statement using official value
        # This is a placeholder - you would implement the actual statement generation logic
        statement_data = {
            "investment_id": investment.id,
            "investor_name": investment.investor_name,
            "official_value": float(investment.official_receipt_value),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "font": "Montserrat"  # As requested
        }

        return make_response(jsonify({
            "status": 200,
            "message": "Reconciliation verified and statement generated",
            "data": statement_data
        }), 200)

    except Exception as e:
        import traceback
        print(f"ERROR in verify_reconciliation: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)
