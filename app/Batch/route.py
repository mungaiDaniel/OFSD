from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from app.database.database import db
from app.Batch.controllers import BatchController
from datetime import datetime

batch_v1 = Blueprint("batch_v1", __name__, url_prefix='/api/v1')

# ==================== BATCH ENDPOINTS ====================

@batch_v1.route('/batches', methods=['POST'])
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
        data = request.get_json()
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


@batch_v1.route('/batches', methods=['GET'])
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


@batch_v1.route('/batches/<int:batch_id>', methods=['GET'])
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


@batch_v1.route('/batches/<int:batch_id>', methods=['PUT'])
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
        data = request.get_json()
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


@batch_v1.route('/batches/<int:batch_id>', methods=['PATCH'])
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
        data = request.get_json()
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


@batch_v1.route('/batches/<int:batch_id>/summary', methods=['GET'])
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


@batch_v1.route('/batches/<int:batch_id>/toggle-active', methods=['PATCH'])
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


@batch_v1.route('/batches/<int:batch_id>/toggle-transferred', methods=['PATCH'])
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


@batch_v1.route('/batches/<int:batch_id>/upload-excel', methods=['POST'])
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
        return BatchController.upload_batch_excel(batch_id, file, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)
