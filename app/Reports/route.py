"""
Reports & Statements Module

Endpoints for generating investor statements, portfolio reports based on ValuationRun and EpochLedger.
All financial values formatted with 2-decimal rounding.
Only 'Committed' valuation runs appear in reports.
"""

from flask import request, Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import func, and_, desc, asc
from decimal import Decimal
from io import BytesIO
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

from app.database.database import db
from app.Investments.model import Investment, EpochLedger
from app.Batch.model import Batch
from app.Batch.core_fund import CoreFund
from app.Valuation.model import ValuationRun
from typing import Optional
import traceback


reports_v1 = Blueprint("reports_v1", __name__, url_prefix="/api/v1/reports")


def format_currency(value):
    """Format value to currency string with 2 decimal places."""
    if value is None:
        return "$0.00"
    return f"${float(value):,.2f}"


def float_2dp(value):
    """Convert to float with 2 decimal places precision."""
    if value is None:
        return 0.00
    return round(float(value), 2)


def _fund_name_from_core_fund(core_fund: Optional[CoreFund]) -> Optional[str]:
    if not core_fund:
        return None
    return (core_fund.fund_name or "").strip() or None


def _get_run_or_404(run_id: int):
    vr = db.session.query(ValuationRun).filter(ValuationRun.id == run_id).first()
    if not vr:
        return None, (jsonify({"status": 404, "message": "Valuation run not found"}), 404)
    if vr.status != "Committed":
        # Avoid null-ledger errors by hiding non-committed runs
        return None, (jsonify({"status": 409, "message": "Valuation run is not committed"}), 409)
    return vr, None


def _run_ledger_aggregates(fund_name: str, epoch_start: datetime, epoch_end: datetime):
    sums = (
        db.session.query(
            func.coalesce(func.sum(EpochLedger.start_balance), 0),
            func.coalesce(func.sum(EpochLedger.deposits), 0),
            func.coalesce(func.sum(EpochLedger.withdrawals), 0),
            func.coalesce(func.sum(EpochLedger.profit), 0),
            func.coalesce(func.sum(EpochLedger.end_balance), 0),
            func.count(EpochLedger.id),
        )
        .filter(
            and_(
                EpochLedger.fund_name == fund_name,
                EpochLedger.epoch_start == epoch_start,
                EpochLedger.epoch_end == epoch_end,
            )
        )
        .first()
    )

    total_opening, total_deposits, total_withdrawals, total_profit, total_closing, investor_count = sums
    return {
        "total_opening_capital": float_2dp(total_opening),
        "total_deposits": float_2dp(total_deposits),
        "total_withdrawals": float_2dp(total_withdrawals),
        "total_profit_distributed": float_2dp(total_profit),
        "total_closing_aum": float_2dp(total_closing),
        "investor_count": int(investor_count or 0),
    }


def _latest_epoch_balances_subquery(as_of: Optional[datetime] = None):
    """
    Helper for portfolio/batch aggregation:
    returns a subquery of the latest EpochLedger row per (internal_client_code, fund_name)
    at or before `as_of` (if provided).
    """
    base = db.session.query(
        EpochLedger.internal_client_code.label("code"),
        EpochLedger.fund_name.label("fund_name"),
        func.max(EpochLedger.epoch_end).label("last_epoch_end"),
    )
    if as_of is not None:
        base = base.filter(EpochLedger.epoch_end <= as_of)
    lep = base.group_by(EpochLedger.internal_client_code, EpochLedger.fund_name).subquery("lep")

    latest = (
        db.session.query(
            EpochLedger.internal_client_code.label("code"),
            EpochLedger.fund_name.label("fund_name"),
            EpochLedger.epoch_start.label("epoch_start"),
            EpochLedger.epoch_end.label("epoch_end"),
            EpochLedger.start_balance.label("start_balance"),
            EpochLedger.deposits.label("deposits"),
            EpochLedger.withdrawals.label("withdrawals"),
            EpochLedger.profit.label("profit"),
            EpochLedger.end_balance.label("end_balance"),
        )
        .join(
            lep,
            and_(
                lep.c.code == EpochLedger.internal_client_code,
                lep.c.fund_name == EpochLedger.fund_name,
                lep.c.last_epoch_end == EpochLedger.epoch_end,
            ),
        )
    ).subquery("latest_epochs")

    return latest


# New canonical endpoints (requested):
# - GET /api/v1/reports
# - GET /api/v1/reports/<valuation_run_id>
# - GET /api/v1/reports/<valuation_run_id>/pdf
# - GET /api/v1/reports/portfolio
# - GET /api/v1/reports/portfolio/multi-batch
# - GET /api/v1/reports/batch/<id>/summary
# - GET /api/v1/reports/batch/<id>/reconciliation


@reports_v1.route("", methods=["GET"])
@jwt_required()
def list_reports():
    """
    List committed valuation runs as report rows.

    Query Parameters:
    - fund_id: optional CoreFund.id filter
    - limit: optional limit (default: 100)
    """
    try:
        fund_id = request.args.get("fund_id", type=int)
        limit = request.args.get("limit", default=100, type=int)

        query = db.session.query(ValuationRun).filter(
            ValuationRun.status == "Committed"
        ).order_by(desc(ValuationRun.epoch_end))

        if fund_id:
            query = query.filter(ValuationRun.core_fund_id == fund_id)

        valuation_runs = query.limit(limit).all()

        result = []
        for vr in valuation_runs:
            fund = db.session.query(CoreFund).filter(CoreFund.id == vr.core_fund_id).first()
            fund_name = _fund_name_from_core_fund(fund)
            if not fund_name:
                # If a fund is missing, skip to avoid null-ledger errors
                continue

            summary = _run_ledger_aggregates(fund_name, vr.epoch_start, vr.epoch_end)

            result.append({
                "id": vr.id,
                "fund_id": vr.core_fund_id,
                "fund_name": fund_name,
                "epoch_start": vr.epoch_start.isoformat(),
                "epoch_end": vr.epoch_end.isoformat(),
                "performance_rate_percent": float_2dp(float(vr.performance_rate) * 100),
                "head_office_total": float_2dp(vr.head_office_total),
                "summary": summary,
                "status": vr.status,
                "created_at": vr.created_at.isoformat(),
            })

        return jsonify({"status": 200, "message": "Reports retrieved", "data": result}), 200

    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@reports_v1.route("/portfolio", methods=["GET"])
@jwt_required()
def portfolio_view():
    """
    Global portfolio AUM per active core fund at an as-of date.

    Query:
      - as_of (optional ISO date/datetime). Defaults to today (UTC date).
    """
    try:
        as_of_raw = (request.args.get("as_of") or "").strip()
        if as_of_raw:
            try:
                as_of = datetime.fromisoformat(as_of_raw.replace("Z", "+00:00"))
            except Exception:
                return jsonify({"status": 400, "message": "Invalid as_of date"}), 400
        else:
            as_of = datetime.utcnow()

        latest = _latest_epoch_balances_subquery(as_of)

        rows = (
            db.session.query(
                CoreFund.id.label("core_fund_id"),
                CoreFund.fund_name.label("core_fund_name"),
                func.coalesce(func.sum(latest.c.end_balance), 0).label("total_aum"),
            )
            .outerjoin(
                latest,
                func.lower(latest.c.fund_name) == func.lower(CoreFund.fund_name),
            )
            .filter(CoreFund.is_active.is_(True))
            .group_by(CoreFund.id, CoreFund.fund_name)
            .order_by(CoreFund.fund_name.asc())
            .all()
        )

        data = [
            {
                "core_fund_id": r.core_fund_id,
                "core_fund_name": r.core_fund_name,
                "total_aum": float_2dp(r.total_aum or 0),
            }
            for r in rows
        ]
        total_global = float_2dp(sum(item["total_aum"] for item in data))

        return jsonify(
            {
                "status": 200,
                "message": "Portfolio AUM retrieved",
                "as_of": as_of.isoformat(),
                "total_global_aum": total_global,
                "funds": data,
            }
        ), 200
    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


def _batch_portfolio_rows(batch_ids, fund_filter: Optional[str] = None):
    """
    Aggregation helper for batch-level portfolio summaries.
    Direct joins: investments -> core_funds -> epoch_ledger
    """
    if not batch_ids:
        return []

    # Direct query approach as requested
    q = (
        db.session.query(
            Batch.id.label("batch_id"),
            Batch.batch_name.label("batch_name"),
            CoreFund.fund_name.label("core_fund_name"),
            func.count(func.distinct(Investment.id)).label("investors_count"),
            func.max(EpochLedger.epoch_end).label("as_of_epoch_end"),
            func.coalesce(func.sum(EpochLedger.start_balance), 0).label("total_opening_capital"),
            func.coalesce(func.sum(EpochLedger.deposits), 0).label("total_deposits"),
            func.coalesce(func.sum(EpochLedger.withdrawals), 0).label("total_withdrawals"),
            func.coalesce(func.sum(EpochLedger.profit), 0).label("total_profit"),
            func.coalesce(func.sum(EpochLedger.end_balance), 0).label("total_closing_aum"),
        )
        .join(Investment, Investment.batch_id == Batch.id)
        .join(CoreFund, Investment.fund_id == CoreFund.id)
        .outerjoin(
            EpochLedger,
            (Investment.internal_client_code == EpochLedger.internal_client_code) &
            (func.lower(CoreFund.fund_name) == func.lower(EpochLedger.fund_name))
        )
        .filter(Batch.id.in_(batch_ids))
    )

    if fund_filter:
        q = q.filter(func.lower(CoreFund.fund_name) == fund_filter.lower())

    rows = (
        q.group_by(Batch.id, Batch.batch_name, CoreFund.fund_name)
        .order_by(Batch.id.asc(), CoreFund.fund_name.asc())
        .all()
    )

    # Attach performance rate from ValuationRun for that "as_of" period (if committed)
    run_keys = {(r.core_fund_name.lower(), r.as_of_epoch_end) for r in rows if r.as_of_epoch_end and r.core_fund_name}
    performance_by_key = {}
    if run_keys:
        # Resolve core_fund_id for names
        names = sorted({name for (name, _) in run_keys})
        core_rows = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name).in_(names)).all()
        core_by_lower = {c.fund_name.lower(): c.id for c in core_rows}

        # Fetch all matching runs
        core_ids = list(core_by_lower.values())
        vr_rows = db.session.query(ValuationRun).filter(
            ValuationRun.core_fund_id.in_(core_ids),
            ValuationRun.status == "Committed",
        ).all()
        vr_by_key = {(vr.core_fund_id, vr.epoch_end): vr for vr in vr_rows}

        for (name_lower, epoch_end) in run_keys:
            core_id = core_by_lower.get(name_lower)
            if not core_id:
                continue
            vr = vr_by_key.get((core_id, epoch_end))
            if vr:
                performance_by_key[(name_lower, epoch_end)] = float_2dp(float(vr.performance_rate) * 100)

    out = []
    for r in rows:
        key = (r.core_fund_name.lower(), r.as_of_epoch_end) if r.core_fund_name and r.as_of_epoch_end else None
        out.append({
            "batch_id": r.batch_id,
            "batch_name": r.batch_name,
            "core_fund_name": r.core_fund_name,
            "as_of_epoch_end": r.as_of_epoch_end.isoformat() if r.as_of_epoch_end else None,
            "performance_rate_percent": performance_by_key.get(key) if key else None,
            "investors_count": int(r.investors_count or 0),
            "total_opening_capital": float_2dp(r.total_opening_capital or 0),
            "total_deposits": float_2dp(r.total_deposits or 0),
            "total_withdrawals": float_2dp(r.total_withdrawals or 0),
            "total_profit": float_2dp(r.total_profit or 0),
            "total_closing_aum": float_2dp(r.total_closing_aum or 0),
        })
    return out


@reports_v1.route("/portfolio/multi-batch", methods=["GET"])
@jwt_required()
def multi_batch_portfolio_excel():
    """
    Legacy endpoint used by GlobalReports "Generate Portfolio Report (Excel)".

    Query:
      - batch_ids: comma-separated list of batch IDs
      - fund_filter (optional): Core fund filter

    Returns:
      - Excel (.xlsx) file with per-batch, per-fund aggregates.
    """
    try:
        batch_ids_raw = (request.args.get("batch_ids") or "").strip()
        if not batch_ids_raw:
            return jsonify({"status": 400, "message": "batch_ids query parameter is required"}), 400

        # Accept comma-separated list; tolerate tokens like "1:1" by taking the first numeric segment.
        batch_ids = []
        for token in batch_ids_raw.split(","):
            t = (token or "").strip()
            if not t:
                continue
            if ":" in t:
                t = t.split(":", 1)[0].strip()
            # keep only digits if someone passes "batch-1"
            digits = "".join(ch for ch in t if ch.isdigit())
            if not digits:
                continue
            batch_ids.append(int(digits))
        batch_ids = sorted(set(batch_ids))
        if not batch_ids:
            return jsonify({"status": 400, "message": "batch_ids must be a comma-separated list of integers"}), 400

        fund_filter = (request.args.get("fund_name") or "").strip() or None

        rows = _batch_portfolio_rows(batch_ids, fund_filter)
        df = pd.DataFrame(rows or [])

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Portfolio")
        output.seek(0)

        filename = f"Portfolio_Report_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@reports_v1.route("/batch/<int:batch_id>/summary", methods=["GET"])
@jwt_required()
def batch_summary_excel(batch_id: int):
    """
    Legacy endpoint used by BatchDetails "Generate Report" / export to Excel.

    Returns a single-batch Excel file with per-fund aggregates.
    """
    try:
        rows = _batch_portfolio_rows([batch_id], fund_filter=None)
        # If there are no committed valuations yet, return an empty excel (not a 500).
        df = pd.DataFrame(rows or [])

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="BatchSummary")
        output.seek(0)

        filename = f"Batch_{batch_id}_Summary_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@reports_v1.route("/batch/<int:batch_id>/reconciliation", methods=["GET"])
@jwt_required()
def batch_reconciliation(batch_id: int):
    """
    JSON reconciliation view for a given batch (used by any legacy UI).
    """
    try:
        rows = _batch_portfolio_rows([batch_id], fund_filter=None)
        total_closing = float_2dp(sum(r["total_closing_aum"] for r in rows))
        total_profit = float_2dp(sum(r["total_profit"] for r in rows))

        return jsonify(
            {
                "status": 200,
                "message": "Batch reconciliation retrieved",
                "data": {
                    "batch_id": batch_id,
                    "lines": rows,
                    "total_closing_aum": total_closing,
                    "total_profit": total_profit,
                },
            }
        ), 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@reports_v1.route("/<int:valuation_run_id>", methods=["GET"])
@jwt_required()
def get_report_detail(valuation_run_id):
    """
    Detailed report based on ValuationRun + EpochLedger.
    """
    try:
        vr, err = _get_run_or_404(valuation_run_id)
        if err:
            return err

        fund = db.session.query(CoreFund).filter(CoreFund.id == vr.core_fund_id).first()
        fund_name = _fund_name_from_core_fund(fund)
        if not fund_name:
            return jsonify({"status": 404, "message": "Core fund not found for this valuation run"}), 404

        # Get epoch ledger entries for this valuation run
        ledger_entries = (
            db.session.query(EpochLedger)
            .filter(
                and_(
                    EpochLedger.fund_name == fund_name,
                    EpochLedger.epoch_start == vr.epoch_start,
                    EpochLedger.epoch_end == vr.epoch_end,
                )
            )
            .order_by(asc(EpochLedger.internal_client_code))
            .all()
        )

        summary = _run_ledger_aggregates(fund_name, vr.epoch_start, vr.epoch_end)

        # Build investor breakdown (resolve investor_name from most recent Investment record)
        investor_breakdown = []
        for entry in ledger_entries:
            inv = (
                db.session.query(Investment)
                .filter(Investment.internal_client_code == entry.internal_client_code)
                .order_by(desc(Investment.date_updated), desc(Investment.id))
                .first()
            )
            investor_breakdown.append({
                "internal_client_code": entry.internal_client_code,
                "investor_name": (inv.investor_name if inv and inv.investor_name else "Unknown"),
                "start_balance": float_2dp(entry.start_balance),
                "deposits": float_2dp(entry.deposits),
                "withdrawals": float_2dp(entry.withdrawals),
                "pro_rata_profit": float_2dp(entry.profit),
                "end_balance": float_2dp(entry.end_balance),
            })

        # Reconciliation: compare local closing AUM to head_office_total (the commit-time lock value)
        reconciliation_diff = float_2dp(Decimal(str(summary["total_closing_aum"])) - Decimal(str(float_2dp(vr.head_office_total))))

        return jsonify({
            "status": 200,
            "message": "Report retrieved",
            "data": {
                "id": vr.id,
                "fund_id": vr.core_fund_id,
                "fund_name": fund_name,
                "epoch_start": vr.epoch_start.isoformat(),
                "epoch_end": vr.epoch_end.isoformat(),
                "performance_rate_percent": float_2dp(float(vr.performance_rate) * 100),
                "head_office_total": float_2dp(vr.head_office_total),
                "status": vr.status,
                "created_at": vr.created_at.isoformat(),
                "summary": {
                    **summary,
                    "reconciliation": {
                        "head_office_total": float_2dp(vr.head_office_total),
                        "local_total_closing_aum": summary["total_closing_aum"],
                        "difference": reconciliation_diff,
                    },
                },
                "investor_breakdown": investor_breakdown,
            }
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@reports_v1.route("/<int:valuation_run_id>/pdf", methods=["GET"])
@jwt_required()
def get_report_pdf(valuation_run_id):
    """
    Generate PDF report for a specific valuation run (AIB-AXYS branded).
    """
    try:
        vr, err = _get_run_or_404(valuation_run_id)
        if err:
            return err

        fund = db.session.query(CoreFund).filter(CoreFund.id == vr.core_fund_id).first()
        fund_name = _fund_name_from_core_fund(fund)
        if not fund_name:
            return jsonify({"status": 404, "message": "Core fund not found for this valuation run"}), 404

        # Get epoch ledger entries
        ledger_entries = db.session.query(EpochLedger).filter(
            and_(
                EpochLedger.fund_name == fund_name,
                EpochLedger.epoch_start == vr.epoch_start,
                EpochLedger.epoch_end == vr.epoch_end,
            )
        ).order_by(asc(EpochLedger.internal_client_code)).all()

        # Calculate summary
        total_start_balance = sum(float(entry.start_balance) for entry in ledger_entries)
        total_deposits = sum(float(entry.deposits) for entry in ledger_entries)
        total_withdrawals = sum(float(entry.withdrawals) for entry in ledger_entries)
        total_profit = sum(float(entry.profit) for entry in ledger_entries)
        total_end_balance = sum(float(entry.end_balance) for entry in ledger_entries)
        
        # Create PDF
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#00005b'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        )
        
        # Header
        story.append(Paragraph("AIB-AXYS Africa", title_style))
        story.append(Paragraph("Valuation Period Report", heading_style))
        story.append(Spacer(1, 0.1*inch))
        
        # Report Info
        period_start = vr.epoch_start.strftime('%B %d, %Y')
        period_end = vr.epoch_end.strftime('%B %d, %Y')
        
        report_data = [
            ['Fund Name:', fund_name],
            ['Performance Period:', f'{period_start} to {period_end}'],
            ['Performance Rate:', f'{float_2dp(float(vr.performance_rate) * 100)}%'],
            ['Report Generated:', datetime.now().strftime('%B %d, %Y')],
        ]
        report_table = Table(report_data, colWidths=[1.5*inch, 3*inch])
        report_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#00005b')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(report_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Financial Summary
        story.append(Paragraph("Financial Summary", heading_style))
        summary_data = [
            ['Opening Capital', format_currency(total_start_balance)],
            ['Total Deposits', format_currency(total_deposits)],
            ['Total Withdrawals', f'({format_currency(total_withdrawals)})'],
            ['Total Profit', format_currency(total_profit)],
            ['Closing AUM', format_currency(total_end_balance)],
            ['Head Office Total', format_currency(vr.head_office_total)],
        ]
        summary_table = Table(summary_data, colWidths=[2.5*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#00005b')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 4), (-1, 5), colors.HexColor('#e6e6f0')),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Investor Breakdown
        if ledger_entries:
            story.append(Paragraph("Investor Breakdown", heading_style))
            breakdown_data = [
                ['Investor Code', 'Name', 'Start Balance', 'Profit', 'End Balance']
            ]
            
            for entry in ledger_entries:
                investments = db.session.query(Investment).filter(
                    Investment.internal_client_code == entry.internal_client_code
                ).all()
                investor_name = investments[0].investor_name if investments else "Unknown"
                
                breakdown_data.append([
                    entry.internal_client_code,
                    investor_name[:20],  # Truncate long names
                    format_currency(float_2dp(entry.start_balance)),
                    format_currency(float_2dp(entry.profit)),
                    format_currency(float_2dp(entry.end_balance)),
                ])
            
            breakdown_table = Table(breakdown_data, colWidths=[1*inch, 1.5*inch, 1.2*inch, 1*inch, 1.2*inch])
            breakdown_table.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00005b')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(breakdown_table)
        
        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        filename = f"Valuation_{fund_name}_{vr.epoch_end.strftime('%Y%m%d')}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


# Backwards-compatible endpoints used by existing frontend service (keep for now)
@reports_v1.route("/valuation-runs", methods=["GET"])
@jwt_required()
def list_valuation_runs_compat():
    return list_reports()


@reports_v1.route("/valuation-runs/<int:valuation_run_id>", methods=["GET"])
@jwt_required()
def get_valuation_run_detail_compat(valuation_run_id):
    return get_report_detail(valuation_run_id)


@reports_v1.route("/valuation-runs/<int:valuation_run_id>/pdf", methods=["GET"])
@jwt_required()
def get_valuation_run_pdf_compat(valuation_run_id):
    return get_report_pdf(valuation_run_id)

