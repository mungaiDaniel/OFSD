from app.Investments.model import Investment
from app.Batch.model import Batch
from app.database.database import db
from flask import jsonify, make_response
from datetime import datetime
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from app.Batch.core_fund import CoreFund


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

            fund_name = (data.get('fund_name') or '').strip()
            fund_id = data.get('fund_id')
            core = None
            if fund_id is not None:
                core = session.query(CoreFund).filter(CoreFund.id == int(fund_id)).first()
            elif fund_name:
                # Normalize to support case-insensitive matches
                fund_name_normalized = fund_name.title()
                core = session.query(CoreFund).filter(db.func.lower(CoreFund.fund_name) == fund_name_normalized.lower()).first()

            if not core:
                return make_response(jsonify({
                    "status": 400,
                    "message": "fund_id or valid fund_name is required"
                }), 400)

            # Create new investment with fund assignment
            investment = cls.model(
                investor_name=data.get('investor_name'),
                investor_email=data.get('investor_email', ''),
                investor_phone=data.get('investor_phone', ''),
                amount_deposited=Decimal(str(data.get('amount_deposited', 0))),
                date_deposited=datetime.fromisoformat(data.get('date_deposited', datetime.utcnow().isoformat())),
                batch_id=data.get('batch_id'),
                fund_id=core.id,
                fund_name=core.fund_name,  # kept for backward compatibility
                internal_client_code=data.get('internal_client_code'),
                date_transferred=datetime.fromisoformat(data['date_transferred']) if data.get('date_transferred') else None
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

    @classmethod
    def upload_excel_for_batch(cls, batch_id, file, session):
        """
        Upload and parse an Excel/CSV file, upserting investor rows into a
        specific batch using (internal_client_code, batch_id) as the key.

        Args:
            batch_id: ID of the target batch (already validated by route)
            file: Werkzeug FileStorage object
            session: database session

        Returns:
            tuple: (json_response, status_code)
        """
        try:
            import pandas as pd
            from io import BytesIO

            # Verify the batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Batch with ID {batch_id} not found"
                }), 404)

            # Read file stream
            file_stream = BytesIO(file.read())

            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file_stream)
                else:
                    df = pd.read_excel(file_stream)
            except Exception as e:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Unable to read file: {str(e)}"
                }), 400)

            # Normalize column names
            df.columns = df.columns.str.lower().str.strip()

            column_mapping = {
                'client name': 'investor_name',
                'internal client code': 'internal_client_code',
                'amount(usd)': 'amount_deposited',
                'funds': 'fund_name',
            }
            df = df.rename(columns=column_mapping)

            required_columns = ['investor_name', 'internal_client_code', 'amount_deposited', 'fund_name']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Missing required columns: {', '.join(missing_columns)}"
                }), 400)

            # Drop rows missing any required field
            df = df.dropna(subset=required_columns)

            investments_processed = 0
            total_amount = 0.0
            errors = []
            core_cache = {}

            for idx, row in df.iterrows():
                try:
                    investor_name = str(row['investor_name']).strip()
                    internal_client_code = str(row['internal_client_code']).strip()
                    amount_deposited = float(row['amount_deposited'])
                    fund_name_raw = str(row['fund_name']).strip()
                    fund_key = fund_name_raw.lower()

                    # Map excel fund name -> core_funds
                    if fund_key not in core_cache:
                        core = session.query(CoreFund).filter(
                            db.func.lower(CoreFund.fund_name) == fund_key
                        ).first()
                        if not core:
                            return make_response(jsonify({
                                "status": 400,
                                "message": f"Unknown core fund '{fund_name_raw}'. Create it first in Admin > Manage Funds."
                            }), 400)
                        core_cache[fund_key] = core
                    core = core_cache[fund_key]

                    # Upsert: check for existing (internal_client_code, batch_id)
                    existing = session.query(Investment).filter(
                        Investment.batch_id == batch_id,
                        Investment.internal_client_code == internal_client_code
                    ).first()

                    if existing:
                        # Update in-place
                        existing.investor_name = investor_name
                        existing.amount_deposited = Decimal(str(amount_deposited))
                        existing.fund_name = core.fund_name
                        existing.fund_id = core.id
                    else:
                        # Insert new row
                        investment = Investment(
                            batch_id=batch_id,
                            investor_name=investor_name,
                            investor_email='',
                            investor_phone='',
                            internal_client_code=internal_client_code,
                            amount_deposited=Decimal(str(amount_deposited)),
                            fund_name=core.fund_name,
                            fund_id=core.id,
                            date_deposited=datetime.utcnow()
                        )
                        session.add(investment)

                    investments_processed += 1
                    total_amount += amount_deposited

                except Exception as row_err:
                    errors.append(f"Row {idx + 2}: {str(row_err)}")

            # Flush to catch any DB-level constraint violations before committing
            try:
                session.flush()
            except IntegrityError as ie:
                session.rollback()
                return make_response(jsonify({
                    "status": 409,
                    "message": "A duplicate investor record was detected for this batch. This usually means two rows share the same Internal Client Code.",
                    "error": {
                        "type": "UniqueViolation",
                        "detail": str(getattr(ie, "orig", ie))
                    }
                }), 409)

            # Recalculate batch total_principal
            batch.total_principal = session.query(
                db.func.sum(Investment.amount_deposited)
            ).filter(
                Investment.batch_id == batch_id
            ).scalar() or 0

            session.commit()

            response_data = {
                "status": 201,
                "message": f"Successfully imported {investments_processed} investor(s) into batch '{batch.batch_name}'",
                "data": {
                    "batch_id": batch_id,
                    "batch_name": batch.batch_name,
                    "imported_count": investments_processed,
                    "total_amount": float(total_amount),
                }
            }
            if errors:
                response_data["warnings"] = errors

            return make_response(jsonify(response_data), 201)

        except SQLAlchemyError as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": "Database error while processing file",
                "error": {"detail": str(e)}
            }), 500)
        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error processing file: {str(e)}"
            }), 500)
