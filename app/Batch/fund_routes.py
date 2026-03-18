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
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from app.Batch.fund import Fund
from sqlalchemy import func
from app.Batch.core_fund import CoreFund

# Create blueprint
fund_v1 = Blueprint("fund_v1", __name__, url_prefix='/api/v1')

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==================== FUND MANAGEMENT ====================

@fund_v1.route('/funds', methods=['GET'])
@jwt_required()
def list_all_funds():
    """Core Fund Management (global).

    Returns all CoreFund records.

    These funds are created dynamically when a batch Excel upload includes a new fund_name.
    """
    try:
        funds = db.session.query(CoreFund).order_by(CoreFund.fund_name.asc()).all()
        data = [{"id": f.id, "fund_name": f.fund_name, "is_active": f.is_active} for f in funds]
        return make_response(jsonify({"status": 200, "message": "Core funds retrieved", "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@fund_v1.route('/funds', methods=['POST'])
@jwt_required()
def create_core_fund():
    """Create a new CoreFund record.

    This endpoint is primarily for UI management and for cases where a fund
    needs to be added manually (e.g. before any batch has been uploaded).
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


@fund_v1.route('/funds/<int:fund_id>', methods=['PATCH'])
@jwt_required()
def update_core_fund(fund_id: int):
    """Update a core fund (name and/or active state)."""
    try:
        data = request.get_json() or {}
        f = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not f:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        if "fund_name" in data and data["fund_name"] is not None:
            name = str(data["fund_name"]).strip()
            normalized = name.title()
            # Prevent duplicate fund names (case-insensitive)
            existing = db.session.query(CoreFund).filter(
                func.lower(CoreFund.fund_name) == normalized.lower(),
                CoreFund.id != fund_id
            ).first()
            if existing:
                return make_response(jsonify({"status": 409, "message": "Fund with that name already exists"}), 409)
            f.fund_name = normalized

        if "is_active" in data:
            f.is_active = bool(data["is_active"])

        db.session.commit()
        return make_response(jsonify({"status": 200, "message": "Fund updated", "data": {"id": f.id, "fund_name": f.fund_name, "is_active": f.is_active}}), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@fund_v1.route('/funds/<int:fund_id>', methods=['DELETE'])
@jwt_required()
def delete_core_fund(fund_id: int):
    """
    Soft-delete by setting is_active=false (keeps history stable).
    """
    try:
        f = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not f:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)
        f.is_active = False
        db.session.commit()
        return make_response(jsonify({"status": 200, "message": "Fund deactivated"}), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

@fund_v1.route('/batches/<int:batch_id>/funds', methods=['GET'])
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


@fund_v1.route('/batches/<int:batch_id>/funds/<fund_name>', methods=['GET'])
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

@fund_v1.route('/batches/<int:batch_id>/funds/<fund_name>/performance', methods=['POST'])
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

@fund_v1.route('/batches/<int:batch_id>/upload-excel', methods=['POST'])
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

@fund_v1.route('/batches/<int:batch_id>/funds/<fund_name>/weekly-update', methods=['GET'])
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

@fund_v1.route('/batches/<int:batch_id>/calculate-all-funds', methods=['POST'])
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

@fund_v1.route('/batches/<int:batch_id>/report/pdf', methods=['GET'])
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
            output_path = f'reports/batch_{batch_id}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf'
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        else:
            output_path = None

        return PDFReportController.generate_batch_pdf_report(batch_id, output_path)

    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@fund_v1.route('/batches/<int:batch_id>/summary', methods=['GET'])
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

        batch = Batch.query.get(batch_id)
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

            funds_data.append({
                "fund_name": fund.fund_name,
                "total_capital": fund_capital,
                "investor_count": len(fund_investments),
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
