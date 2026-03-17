from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from app.database.database import db
from app.Investments.controllers import InvestmentController

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
