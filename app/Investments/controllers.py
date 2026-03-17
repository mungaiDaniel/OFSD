from app.Investments.model import Investment
from app.Batch.model import Batch
from app.database.database import db
from flask import jsonify, make_response
from datetime import datetime
from decimal import Decimal


class InvestmentController:
    """Controller for Investment operations"""
    
    model = Investment

    @classmethod
    def add_investment(cls, data, session):
        """
        Add a new investment to a batch with fund assignment.
        
        Args:
            data: dict with investor_name, investor_email, investor_phone, amount_deposited, 
                  batch_id, date_deposited, fund_name, internal_client_code
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            # Validate batch exists
            batch = session.query(Batch).filter(Batch.id == data.get('batch_id')).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Create new investment with fund assignment
            investment = cls.model(
                investor_name=data.get('investor_name'),
                investor_email=data.get('investor_email', ''),
                investor_phone=data.get('investor_phone', ''),
                amount_deposited=Decimal(str(data.get('amount_deposited', 0))),
                date_deposited=datetime.fromisoformat(data.get('date_deposited', datetime.utcnow().isoformat())),
                batch_id=data.get('batch_id'),
                fund_name=data.get('fund_name', 'Default').lower(),  # e.g., 'axiom', 'atium'
                internal_client_code=data.get('internal_client_code'),
                date_transferred=datetime.fromisoformat(data['date_deposited']) if 'date_deposited' in data else None
            )

            investment.save(session)

            return make_response(jsonify({
                "status": 201,
                "message": "Investment added successfully",
                "data": {
                    "investment_id": investment.id,
                    "investor_name": investment.investor_name,
                    "investor_email": investment.investor_email,
                    "investor_phone": investment.investor_phone,
                    "internal_client_code": investment.internal_client_code,
                    "amount_deposited": float(investment.amount_deposited),
                    "date_deposited": investment.date_deposited.isoformat(),
                    "fund_name": investment.fund_name,
                    "batch_id": investment.batch_id
                }
            }), 201)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid data format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error adding investment: {str(e)}"
            }), 500)

    @classmethod
    def get_investment_by_id(cls, investment_id, session):
        """
        Get an investment by ID.
        
        Args:
            investment_id: ID of the investment
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            investment = session.query(Investment).filter(Investment.id == investment_id).first()
            
            if not investment:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Investment not found"
                }), 404)

            return make_response(jsonify({
                "status": 200,
                "message": "Investment retrieved successfully",
                "data": {
                    "investment_id": investment.id,
                    "investor_name": investment.investor_name,
                    "investor_email": investment.investor_email,
                    "investor_phone": investment.investor_phone,
                    "internal_client_code": investment.internal_client_code,
                    "amount_deposited": float(investment.amount_deposited),
                    "date_deposited": investment.date_deposited.isoformat(),
                    "fund_name": investment.fund_name,
                    "batch_id": investment.batch_id
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving investment: {str(e)}"
            }), 500)

    @classmethod
    def get_investments_by_batch(cls, batch_id, session):
        """
        Get all investments for a batch.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            # Validate batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()

            investments_data = [
                {
                    "investment_id": inv.id,
                    "investor_name": inv.investor_name,
                    "investor_email": inv.investor_email,
                    "investor_phone": inv.investor_phone,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    "date_deposited": inv.date_deposited.isoformat(),
                    "fund_name": inv.fund_name
                }
                for inv in investments
            ]

            total_principal = sum(float(inv.amount_deposited) for inv in investments)

            return make_response(jsonify({
                "status": 200,
                "message": "Investments retrieved successfully",
                "batch_id": batch_id,
                "count": len(investments_data),
                "total_principal": total_principal,
                "data": investments_data
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving investments: {str(e)}"
            }), 500)

    @classmethod
    def update_investment(cls, investment_id, data, session):
        """
        Update an investment.
        
        Args:
            investment_id: ID of the investment
            data: dict with fields to update
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            investment = session.query(Investment).filter(Investment.id == investment_id).first()
            
            if not investment:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Investment not found"
                }), 404)

            # Update allowed fields
            if 'investor_name' in data:
                investment.investor_name = data['investor_name']
            if 'investor_email' in data:
                investment.investor_email = data['investor_email']
            if 'investor_phone' in data:
                investment.investor_phone = data['investor_phone']
            if 'amount_deposited' in data:
                investment.amount_deposited = Decimal(str(data['amount_deposited']))
            if 'date_deposited' in data:
                investment.date_deposited = datetime.fromisoformat(data['date_deposited'])
            if 'fund_name' in data:
                investment.fund_name = data['fund_name'].lower()
            if 'internal_client_code' in data:
                investment.internal_client_code = data['internal_client_code']

            session.commit()

            return make_response(jsonify({
                "status": 200,
                "message": "Investment updated successfully",
                "data": {
                    "investment_id": investment.id,
                    "investor_name": investment.investor_name,
                    "investor_email": investment.investor_email,
                    "investor_phone": investment.investor_phone,
                    "internal_client_code": investment.internal_client_code,
                    "amount_deposited": float(investment.amount_deposited),
                    "date_deposited": investment.date_deposited.isoformat(),
                    "fund_name": investment.fund_name,
                    "batch_id": investment.batch_id
                }
            }), 200)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid data format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error updating investment: {str(e)}"
            }), 500)

    @classmethod
    def delete_investment(cls, investment_id, session):
        """
        Delete an investment.
        
        Args:
            investment_id: ID of the investment
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            investment = session.query(Investment).filter(Investment.id == investment_id).first()
            
            if not investment:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Investment not found"
                }), 404)

            session.delete(investment)
            session.commit()

            return make_response(jsonify({
                "status": 200,
                "message": "Investment deleted successfully"
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error deleting investment: {str(e)}"
            }), 500)
