"""
Multi-Fund and Advanced Batch Routes

These routes handle:
- Fund management (create, list, get details)
- Fund-specific performance uploads
- Multi-fund pro-rata calculations
- Excel bulk uploads
- Weekly live calculations
- PDF report generation
"""

from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from app.database.database import db
from app.Batch.fund_controllers import (
    FundController,
    BatchFundPerformanceController,
    ExcelUploadController,
    BatchLiveWeeklyController,
    PDFReportController
)
from app.logic.pro_rata_service import MultiFundProRataService
from datetime import datetime, timezone
import os
from werkzeug.utils import secure_filename
from app.Batch.fund import Fund
from sqlalchemy import func, or_, distinct
from app.Batch.core_fund import CoreFund, get_fund_scoped_or_404
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Funds.investor_shares import InvestorShares
from app.database.product_type import FUNDS, SHARES

# Create blueprint
fund_v1 = Blueprint("fund_v1", __name__, url_prefix='/')

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==================== FUND MANAGEMENT ====================

def _list_funds_impl(product):
    """
    Core Fund Management (global), scoped to one product — shared by
    GET /api/v1/funds (FUNDS) and GET /api/v1/shares (SHARES), Task 8.
    Returns CoreFund records of that product with LIVE AUM and investor counts.
    """
    funds = db.session.query(CoreFund).filter(
        CoreFund.is_active == True, CoreFund.product_type == product,
    ).order_by(CoreFund.fund_name.asc()).all()
    data = []
    for f in funds:
        # Aggregate in SQL instead of loading every Investment row for the
        # fund into Python — with 100k+ investments this used to load the
        # whole fund's rows once per fund just to sum() in a loop.
        fund_scope = or_(
            Investment.fund_id == f.id,
            (Investment.fund_id == None) & (func.lower(Investment.fund_name) == f.fund_name.lower())
        )
        total_aum_raw, investor_count = db.session.query(
            func.coalesce(func.sum(Investment.amount_deposited), 0),
            func.count(distinct(Investment.internal_client_code)),
        ).filter(fund_scope).one()
        total_aum = float(total_aum_raw or 0)
        investor_count = investor_count or 0
        data.append({
            "id": f.id,
            "fund_name": f.fund_name,
            "fund_code": f.fund_code,
            "description": f.description,
            "product_type": f.product_type,
            "is_active": f.is_active,
            "total_aum": total_aum,
            "investor_count": investor_count
        })
    return make_response(jsonify({"status": 200, "message": "Core funds retrieved", "data": data}), 200)


@fund_v1.route('/api/v1/funds', methods=['GET'])
@jwt_required()
def list_all_funds():
    """GET /api/v1/funds — FUNDS only. See _list_funds_impl."""
    try:
        return _list_funds_impl(FUNDS)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@fund_v1.route('/api/v1/shares', methods=['GET'])
@jwt_required()
def list_all_shares():
    """GET /api/v1/shares — Task 8 alias of /funds, scoped to SHARES."""
    try:
        return _list_funds_impl(SHARES)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _get_single_fund_impl(fund_id, product):
    """
    Get single fund with live performance/AUM tracking and respective
    batches, scoped to one product — shared by GET /api/v1/funds/<id>
    (FUNDS) and GET /api/v1/shares/<id> (SHARES), Task 8. A fund_id
    belonging to the other product 404s exactly like a nonexistent id.
    """
    f, error_response = get_fund_scoped_or_404(fund_id, product)
    if error_response:
        return error_response
    try:
        # Aggregate in SQL instead of loading every Investment row for the fund
        # into Python — with 100k+ investments this used to materialize the
        # entire fund's row set on every fund-detail page load.
        fund_scope = or_(
            Investment.fund_id == f.id,
            (Investment.fund_id == None) & (func.lower(Investment.fund_name) == f.fund_name.lower())
        )
        total_aum_raw, investor_count = db.session.query(
            func.coalesce(func.sum(Investment.amount_deposited), 0),
            func.count(distinct(Investment.internal_client_code)),
        ).filter(fund_scope).one()
        total_aum = float(total_aum_raw or 0)
        investor_count = investor_count or 0

        batch_ids = [
            bid for (bid,) in db.session.query(Investment.batch_id)
            .filter(fund_scope, Investment.batch_id.isnot(None))
            .distinct().all()
        ]
        batches = db.session.query(Batch).filter(Batch.id.in_(batch_ids)).all() if batch_ids else []

        batches_data = []
        for b in batches:
            b_aum_raw, b_inv_count = db.session.query(
                func.coalesce(func.sum(Investment.amount_deposited), 0),
                func.count(distinct(Investment.internal_client_code)),
            ).filter(Investment.batch_id == b.id, fund_scope).one()
            b_aum = float(b_aum_raw or 0)
            b_inv_count = b_inv_count or 0
            batches_data.append({
                "batch_id": b.id,
                "batch_name": b.batch_name,
                "total_aum": b_aum,
                "investor_count": b_inv_count,
                "date_deployed": b.date_deployed.isoformat() if b.date_deployed else None,
                "is_active": b.is_active
            })

        # Share classes for this fund
        share_classes = db.session.query(ShareClass).filter(
            ShareClass.core_fund_id == fund_id,
            ShareClass.is_active == True
        ).order_by(ShareClass.class_name).all()

        share_classes_data = []
        for sc in share_classes:
            # Primary: InvestorShares reflects current class assignments after any manual moves
            total_sc_shares = db.session.query(
                func.sum(InvestorShares.shares_owned)
            ).filter(
                InvestorShares.share_class_id == sc.id,
                InvestorShares.is_active == True
            ).scalar()

            # Fallback: if InvestorShares has no records for this class, use Batch.total_shares
            if not total_sc_shares:
                total_sc_shares = db.session.query(
                    func.sum(Batch.total_shares)
                ).filter(
                    Batch.share_class_id == sc.id,
                    Batch.total_shares.isnot(None)
                ).scalar()

            # Investor count: use InvestorShares so moved investors are counted in their new class
            investor_count_sc = db.session.query(
                func.count(func.distinct(InvestorShares.investment_id))
            ).filter(
                InvestorShares.share_class_id == sc.id,
                InvestorShares.is_active == True
            ).scalar() or 0

            # Batch count for this share class
            batch_count = db.session.query(func.count(Batch.id)).filter(
                Batch.share_class_id == sc.id
            ).scalar() or 0

            share_classes_data.append({
                "id": sc.id,
                "class_name": sc.class_name,
                "class_code": sc.class_code,
                "currency": sc.currency,
                "current_nav": float(sc.current_nav) if sc.current_nav else None,
                "total_shares": round(float(total_sc_shares), 4) if total_sc_shares else 0.0,
                "investor_count": investor_count_sc,
                "batch_count": batch_count,
            })

        data = {
            "id": f.id,
            "fund_name": f.fund_name,
            "fund_code": f.fund_code,
            "description": f.description,
            "product_type": f.product_type,
            "is_active": f.is_active,
            "total_aum": total_aum,
            "investor_count": investor_count,
            "batches": batches_data,
            "share_classes": share_classes_data,
        }
        return make_response(jsonify({"status": 200, "message": "Fund retrieved", "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@fund_v1.route('/api/v1/funds/<int:fund_id>', methods=['GET'])
@jwt_required()
def get_single_fund(fund_id: int):
    """GET /api/v1/funds/<id> — FUNDS only. See _get_single_fund_impl."""
    return _get_single_fund_impl(fund_id, FUNDS)


@fund_v1.route('/api/v1/shares/<int:fund_id>', methods=['GET'])
@jwt_required()
def get_single_share_fund(fund_id: int):
    """GET /api/v1/shares/<id> — Task 8 alias of /funds/<id>, scoped to SHARES."""
    return _get_single_fund_impl(fund_id, SHARES)


@fund_v1.route('/api/v1/funds/core', methods=['POST'])
@jwt_required()
def create_core_fund():
    """Create a new CoreFund record.

    This endpoint is primarily for UI/admin management and is separate from
    the NAV-specific fund creation endpoint.
    """
    try:
        data = request.get_json() or {}
        # Accept both shapes:
        # - { "fund_name": "Axiom" }  (legacy)
        # - { "name": "Axiom", "status": "Active" } (UI)
        name = (data.get("name") or data.get("fund_name") or "").strip()
        if not name:
            return make_response(jsonify({"status": 400, "message": "fund_name is required"}), 400)

        normalized_name = name.title()

        existing = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == normalized_name.lower()).first()
        if existing:
            return make_response(jsonify({"status": 409, "message": "Fund already exists"}), 409)

        status = (data.get("status") or "Active").strip().lower()
        is_active = status in ("active", "true", "1", "yes")

        f = CoreFund(fund_name=normalized_name, is_active=is_active)
        db.session.add(f)
        db.session.commit()
        return make_response(
            jsonify(
                {
                    "status": 201,
                    "message": "Fund created",
                    "data": {"id": f.id, "fund_name": f.fund_name, "is_active": f.is_active},
                }
            ),
            201,
        )
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _update_fund_impl(fund_id, product):
    """
    Edit a fund/share, scoped to one product — shared by
    PATCH /api/v1/funds/<id> (FUNDS) and PATCH /api/v1/shares/<id> (SHARES).
    Task 12: role check, validation, uniqueness, deactivation blockers,
    optimistic concurrency, rename cascade and audit logging all live in
    app/Funds/edit_service.py::update_fund. product_type stays immutable.
    """
    from app.Funds.edit_service import update_fund
    return update_fund(fund_id, product)


@fund_v1.route('/api/v1/funds/<int:fund_id>', methods=['PATCH'])
@jwt_required()
def update_core_fund(fund_id: int):
    """PATCH /api/v1/funds/<id> — FUNDS only. See _update_fund_impl."""
    return _update_fund_impl(fund_id, FUNDS)


@fund_v1.route('/api/v1/shares/<int:fund_id>', methods=['PATCH'])
@jwt_required()
def update_share_fund(fund_id: int):
    """PATCH /api/v1/shares/<id> — Task 8 alias of /funds/<id>, scoped to SHARES."""
    return _update_fund_impl(fund_id, SHARES)


def _delete_fund_impl(fund_id, product):
    """
    Completely remove a fund from the database (including related
    investments & withdrawals), then hide it from UI — scoped to one
    product, shared by DELETE /api/v1/funds/<id> (FUNDS) and
    DELETE /api/v1/shares/<id> (SHARES), Task 8.
    """
    f, error_response = get_fund_scoped_or_404(fund_id, product)
    if error_response:
        return error_response
    try:
        # Share classes reference the fund (share_classes.core_fund_id), so they
        # must go first. Only empty ones are removed: a class with batches,
        # holdings, NAV history or valuation runs would take that history with
        # it, so refuse instead and suggest deactivating.
        from app.Funds.share_class import ShareClass
        from app.Funds.edit_service import share_class_currency_blockers
        from app.Valuation.model import ValuationRun

        classes = db.session.query(ShareClass).filter(ShareClass.core_fund_id == fund_id).all()
        blockers = [
            f"{sc.class_code}: {', '.join(reasons)}"
            for sc in classes
            if (reasons := [r for r in share_class_currency_blockers(sc) if not r.endswith(("deposit", "deposits"))])
        ]
        valuation_runs = db.session.query(func.count(ValuationRun.id)).filter(ValuationRun.core_fund_id == fund_id).scalar() or 0
        if valuation_runs:
            blockers.append(f"{valuation_runs} valuation run{'s' if valuation_runs != 1 else ''}")
        if blockers:
            return make_response(jsonify({
                "status": 409,
                "message": (
                    f"Can't delete {f.fund_name}: it still has history ({'; '.join(blockers)}). "
                    "Deactivate it instead."
                ),
            }), 409)

        # Delete related dependent rows before deleting fund to avoid FK constraints
        db.session.query(Investment).filter(Investment.fund_id == fund_id).delete(synchronize_session=False)
        from app.Investments.model import Withdrawal
        db.session.query(Withdrawal).filter(Withdrawal.fund_id == fund_id).delete(synchronize_session=False)

        # Optional: remove epoch-ledger rows by fund_name (if full deletion desired)
        from app.Investments.model import EpochLedger
        db.session.query(EpochLedger).filter(EpochLedger.fund_name == f.fund_name).delete(synchronize_session=False)

        # Deposits were removed above, so these classes are now empty.
        for sc in classes:
            db.session.delete(sc)
        db.session.flush()

        db.session.delete(f)
        db.session.commit()

        return make_response(jsonify({"status": 200, "message": "Fund deleted"}), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@fund_v1.route('/api/v1/funds/<int:fund_id>', methods=['DELETE'])
@jwt_required()
def delete_core_fund(fund_id: int):
    """DELETE /api/v1/funds/<id> — FUNDS only. See _delete_fund_impl."""
    return _delete_fund_impl(fund_id, FUNDS)


@fund_v1.route('/api/v1/shares/<int:fund_id>', methods=['DELETE'])
@jwt_required()
def delete_share_fund(fund_id: int):
    """DELETE /api/v1/shares/<id> — Task 8 alias of /funds/<id>, scoped to SHARES."""
    return _delete_fund_impl(fund_id, SHARES)

@fund_v1.route('/api/v1/batches/<int:batch_id>/funds', methods=['GET'])
@jwt_required()
def get_batch_funds(batch_id):
    """
    Get all funds within a batch
    
    Response:
    {
        "data": [
            {
                "id": 1,
                "fund_name": "Axiom",
                "total_capital": 350000.00,
                "investor_count": 7,
                "expected_close_date": "2026-03-31T00:00:00"
            }
        ]
    }
    """
    try:
        session = db.session
        return FundController.get_all_funds_for_batch(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@fund_v1.route('/api/v1/batches/<int:batch_id>/funds/<fund_name>', methods=['GET'])
@jwt_required()
def get_fund_details(batch_id, fund_name):
    """
    Get detailed summary for a specific fund
    
    Response includes:
    - Fund metadata
    - All investments in fund
    - Performance history
    - Distributions (if calculated)
    """
    try:
        session = db.session
        return FundController.get_fund_summary(batch_id, fund_name, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


# ==================== FUND PERFORMANCE ====================

@fund_v1.route('/api/v1/batches/<int:batch_id>/funds/<fund_name>/performance', methods=['POST'])
@jwt_required()
def record_fund_performance(batch_id, fund_name):
    """
    Record monthly (or periodic) performance for a specific fund.
    
    Request Body:
    {
        "gross_profit": 150000.00,
        "transaction_costs": 5000.00,
        "reporting_period": "MONTHLY"
    }
    
    Note: This is fund-specific, so you can upload 'Axiom' performance
    without affecting 'Atium' calculations.
    """
    try:
        data = request.get_json()
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)

        session = db.session
        return BatchFundPerformanceController.create_fund_performance(
            batch_id, fund_name, data, session
        )
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


# ==================== EXCEL UPLOAD ====================

@fund_v1.route('/api/v1/batches/<int:batch_id>/upload-excel', methods=['POST'])
@jwt_required()
def upload_investments_excel(batch_id):
    """
    ⭐ BULK UPLOAD ENDPOINT ⭐
    
    Upload investments from Excel file.
    Automatically groups investors by 'fund' column and creates funds if needed.
    
    Excel Format (required columns):
    - investor_name (String)
    - investor_email (Email)
    - internal_client_code (Unique ID)
    - amount(usd) (Numeric, e.g., 50000.00)
    - fund (String: 'Axiom', 'Atium', etc.)
    - date_transferred (DateTime, optional)
    
If 'fund' column is omitted, all investors will be assigned to a single "Default" fund.
    
    Request: multipart/form-data with file
    
    Response (201):
    {
        "created_count": 12,
        "funds": {
            "Axiom": {
                "fund_id": 1,
                "investor_count": 7,
                "total_capital": 350000.00
            },
            "Atium": {
                "fund_id": 2,
                "investor_count": 5,
                "total_capital": 250000.00
            }
        }
    }
    """
    try:
        # Check if file in request
        if 'file' not in request.files:
            return make_response(jsonify({
                "status": 400,
                "message": "No file provided"
            }), 400)

        file = request.files['file']

        if file.filename == '':
            return make_response(jsonify({
                "status": 400,
                "message": "No file selected"
            }), 400)

        if not allowed_file(file.filename):
            return make_response(jsonify({
                "status": 400,
                "message": "File must be Excel (.xlsx or .xls)"
            }), 400)

        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Upload investments
        session = db.session
        result = ExcelUploadController.upload_investments_from_excel(
            batch_id, filepath, session
        )

        # Clean up file
        try:
            os.remove(filepath)
        except:
            pass

        return result

    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


# ==================== LIVE WEEKLY CALCULATIONS ====================

@fund_v1.route('/api/v1/batches/<int:batch_id>/funds/<fund_name>/weekly-update', methods=['GET'])
@jwt_required()
def get_fund_weekly_update(batch_id, fund_name):
    """
    Get live weekly update for a fund.
    
    Shows current accrued days and capital without waiting for monthly performance.
    
    Response:
    {
        "fund_name": "Axiom",
        "as_of_date": "2026-03-23T00:00:00",
        "total_capital": 350000.00,
        "investor_count": 7,
        "investors": [
            {
                "investor_name": "John Doe",
                "internal_client_code": "AXIOM-001",
                "amount_deposited": 50000.00,
                "days_active": 13,
                "expected_close_date": "2026-03-31T00:00:00"
            }
        ]
    }
    """
    try:
        session = db.session
        return BatchLiveWeeklyController.get_weekly_update(batch_id, fund_name, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


# ==================== MULTI-FUND PRO-RATA CALCULATION ====================

@fund_v1.route('/api/v1/batches/<int:batch_id>/calculate-all-funds', methods=['POST'])
@jwt_required()
def calculate_all_funds_pro_rata(batch_id):
    """
    ⭐⭐⭐ CALCULATE ALL FUNDS PRO-RATA ⭐⭐⭐
    
    This is the main endpoint for fund distribution calculations.
    
    Requirements:
    1. All funds must have performance data recorded
    2. Excel upload must be completed
    3. All investors must be assigned to funds
    
    Request Body:
    {
        "performance_data": {
            "Axiom": 1,     // Fund name -> Performance Record ID
            "Atium": 2
        }
    }
    
    Response (200):
    {
        "batch_id": 1,
        "distribution_count": 12,
        "total_batch_value": 145000.00,
        "funds": {
            "Axiom": {
                "investor_count": 7,
                "total_allocated": 85000.00,
                "distributions": [...]
            },
            "Atium": {
                "investor_count": 5,
                "total_allocated": 60000.00,
                "distributions": [...]
            }
        }
    }
    """
    try:
        data = request.get_json()
        if not data or 'performance_data' not in data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body must include performance_data"
            }), 400)

        performance_data = data['performance_data']  # dict: fund_name -> performance_id

        # Call service
        success, message, summary = MultiFundProRataService.calculate_batch_all_funds(
            batch_id, performance_data
        )

        if not success:
            return make_response(jsonify({
                "status": 400,
                "message": message
            }), 400)

        return make_response(jsonify({
            "status": 200,
            "message": message,
            "data": summary
        }), 200)

    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


# ==================== REPORTING ====================

@fund_v1.route('/api/v1/batches/<int:batch_id>/report/pdf', methods=['GET'])
@jwt_required()
def generate_batch_report_pdf(batch_id):
    """
    Generate comprehensive PDF statement for a batch.
    
    PDF includes:
    - Batch summary
    - All funds and their performance
    - Individual investor positions
    - Profit distributions by fund
    
    Query Parameters:
    - download: "true" to download file, "false" to return JSON
    
    Response: PDF bytes or JSON confirmation
    """
    try:
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            output_path = f'reports/batch_{batch_id}_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.pdf'
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        else:
            output_path = None

        return PDFReportController.generate_batch_pdf_report(batch_id, output_path)

    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@fund_v1.route('/api/v1/batches/<int:batch_id>/summary', methods=['GET'])
@jwt_required()
def get_comprehensive_batch_summary(batch_id):
    """
    Get comprehensive batch summary with fund breakdown.
    
    Shows:
    - Batch metadata
    - All funds with investor count and capital
    - Cumulative performance by fund
    - Total batch value
    - Distribution history
    """
    try:
        from app.Batch.model import Batch
        from app.Batch.fund import Fund
        from app.Investments.model import Investment
        from app.Performance.pro_rata_distribution import ProRataDistribution

        batch = db.session.get(Batch, batch_id)
        if not batch:
            return make_response(jsonify({
                "status": 404,
                "message": "Batch not found"
            }), 404)

        # Get all funds
        funds = Fund.query.filter_by(batch_id=batch_id).all()

        funds_data = []
        total_batch_capital = 0

        for fund in funds:
            fund_investments = Investment.query.filter_by(
                batch_id=batch_id,
                fund_name=fund.fund_name
            ).all()

            fund_distributions = ProRataDistribution.query.filter_by(
                batch_id=batch_id,
                fund_name=fund.fund_name
            ).all()

            fund_capital = sum(float(inv.amount_deposited) for inv in fund_investments)
            total_distributed = sum(float(d.profit_allocated) for d in fund_distributions) if fund_distributions else 0
            # Count unique investors by distinct internal_client_code
            unique_fund_investors = db.session.query(
                func.count(distinct(Investment.internal_client_code))
            ).filter(
                Investment.fund_id == fund.id,
                Investment.batch_id == batch.id
            ).scalar() or 0

            funds_data.append({
                "fund_name": fund.fund_name,
                "total_capital": fund_capital,
                "investor_count": unique_fund_investors,
                "performance_records": len(fund.performance_records),
                "total_distributed": total_distributed,
                "expected_close_date": fund.expected_close_date.isoformat()
            })

            total_batch_capital += fund_capital

        return make_response(jsonify({
            "status": 200,
            "message": "Batch summary retrieved",
            "data": {
                "batch_id": batch.id,
                "batch_name": batch.batch_name,
                "certificate_number": batch.certificate_number,
                "date_deployed": batch.date_deployed.isoformat(),
                "expected_close_date": batch.expected_close_date.isoformat(),
                "total_batch_capital": total_batch_capital,
                "fund_count": len(funds),
                "funds": funds_data
            }
        }), 200)

    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)
