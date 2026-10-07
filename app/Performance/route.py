from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from app.database.database import db
from app.Performance.controllers import PerformanceController

performance_v1 = Blueprint("performance_v1", __name__, url_prefix='/')

# ==================== PERFORMANCE ENDPOINTS ====================

@performance_v1.route('/api/v1/batches/<int:batch_id>/performance', methods=['POST'])
@jwt_required()
def create_performance(batch_id):
    """
    Create performance data for a batch and close it
    
    Request Body:
    {
        "gross_profit": 150000.00,
        "transaction_costs": 5000.00,
        "date_closed": "2026-03-31T00:00:00"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return make_response(jsonify({
                "status": 400,
                "message": "Request body is required"
            }), 400)
        
        data['batch_id'] = batch_id
        session = db.session
        return PerformanceController.create_performance(data, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@performance_v1.route('/api/v1/batches/<int:batch_id>/performance', methods=['GET'])
@jwt_required()
def get_performance(batch_id):
    """
    Get ALL performance data for a batch (across all funds).
    
    Returns array of performance records, one per fund.
    
    Optional Query Parameter:
    - fund_name: If provided, returns performance for just that fund
    Examples:
    - GET /api/v1/batches/1/performance → Returns all funds
    - GET /api/v1/batches/1/performance?fund_name=axiom → Returns only axiom
    """
    try:
        session = db.session
        
        # Check if fund_name filter is requested
        fund_name = request.args.get('fund_name')
        if fund_name:
            return PerformanceController.get_performance_by_fund(batch_id, fund_name, session)
        else:
            return PerformanceController.get_performance_by_batch(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@performance_v1.route('/api/v1/batches/<int:batch_id>/calculate-pro-rata', methods=['POST'])
@jwt_required()
def calculate_pro_rata(batch_id):
    """
    ⭐ TRIGGER PRO-RATA CALCULATION FOR A FUND ⭐
    
    This endpoint must be called AFTER performance data is entered.
    It calculates profit distributions for investors in a specific fund.
    
    Query Parameters:
    - fund_name: Name of the fund (e.g., 'axiom', 'atium') - REQUIRED
    
    Request Body:
    {
        "fund_name": "axiom"  // Or as query param: ?fund_name=axiom
    }
    """
    try:
        # Get fund_name from query params or request body
        fund_name = request.args.get('fund_name')
        data = request.get_json(silent=True) or {}
        if not fund_name:
            fund_name = data.get('fund_name')

        if not fund_name:
            return make_response(jsonify({
                "status": 400,
                "message": "fund_name parameter is required (query param or request body)"
            }), 400)

        session = db.session
        return PerformanceController.calculate_pro_rata(batch_id, fund_name, session, extra_data=data)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@performance_v1.route('/api/v1/batches/<int:batch_id>/distributions', methods=['GET'])
@jwt_required()
def get_distributions(batch_id):
    """
    Get all pro-rata distributions for a batch (grouped by fund).
    
    Returns detailed breakdown for all funds:
    - Investor name and contact
    - Amount deposited and deposit date
    - Days active in the fund
    - Weighted capital calculation
    - Profit share percentage
    - Profit allocated (actual amount)
    
    Response structure:
    {
        "funds": {
            "axiom": [...],
            "atium": [...]
        }
    }
    """
    try:
        session = db.session
        return PerformanceController.get_distributions_for_batch(batch_id, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)


@performance_v1.route('/api/v1/batches/<int:batch_id>/funds/<fund_name>/distributions', methods=['GET'])
@jwt_required()
def get_distributions_by_fund(batch_id, fund_name):
    """
    Get pro-rata distributions for a specific fund in a batch.
    
    Path Parameters:
    - batch_id: ID of the batch
    - fund_name: Name of the fund (e.g., 'axiom', 'atium')
    
    Returns detailed breakdown:
    - Investor name and contact
    - Amount deposited and deposit date
    - Days active in the fund
    - Weighted capital calculation
    - Profit share percentage
    - Profit allocated (actual amount)
    """
    try:
        session = db.session
        return PerformanceController.get_distributions_by_fund(batch_id, fund_name, session)
    except Exception as e:
        return make_response(jsonify({
            "status": 500,
            "message": f"Error: {str(e)}"
        }), 500)
