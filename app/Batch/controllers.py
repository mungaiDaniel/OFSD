from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger
from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
from app.Batch.core_fund import CoreFund
from app.database.database import db
from flask import jsonify, make_response
from datetime import datetime, timedelta
from marshmallow import ValidationError
from sqlalchemy import select


class BatchController:
    """Controller for Batch operations"""
    
    model = Batch

    @classmethod
    def create_batch(cls, data, session):
        """
        Create a new batch (fund container).
        Two-stage creation: only batch_name is required initially.
        
        Args:
            data: dict with batch_name (required), certificate_number, date_deployed, duration_days (optional)
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            # Validate required field
            batch_name = data.get('batch_name')
            if not batch_name:
                return make_response(jsonify({
                    "status": 400,
                    "message": "Batch name is required"
                }), 400)
            
            # Get optional fields
            certificate_number = data.get('certificate_number')
            date_deployed_str = data.get('date_deployed')
            
            # Check if certificate number already exists (only if provided)
            if certificate_number:
                existing = session.query(Batch).filter(
                    Batch.certificate_number == certificate_number
                ).first()
                
                if existing:
                    return make_response(jsonify({
                        "status": 409,
                        "message": "Batch with that certificate number already exists"
                    }), 409)

            # Parse date_deployed if provided
            date_deployed = None
            if date_deployed_str:
                try:
                    date_deployed = datetime.fromisoformat(date_deployed_str)
                except ValueError:
                    return make_response(jsonify({
                        "status": 400,
                        "message": f"Invalid date format: {date_deployed_str}"
                    }), 400)

            # Create new batch with optional fields as None
            batch = cls.model(
                batch_name=batch_name,
                certificate_number=certificate_number,
                date_deployed=date_deployed,
                duration_days=data.get('duration_days', 30),
                is_active=False  # New batches start as inactive
            )

            batch.save(session)

            # Determine status based on date_deployed
            status = 'Pending' if not date_deployed else 'Active'

            return make_response(jsonify({
                "status": 201,
                "message": "Batch created successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if date_deployed else None,
                    "is_active": batch.is_active,
                    "status": status
                }
            }), 201)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error creating batch: {str(e)}"
            }), 500)

    @classmethod
    def get_batch_by_id(cls, batch_id, session):
        """
        Get a batch by ID with all details and investments.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investments
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()

            investments_data = [
                {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    # Prefer the FK relationship fund name, fall back to the legacy fund_name field
                    "fund_id": inv.fund_id,
                    "fund_name": inv.fund.fund_name if inv.fund else inv.fund_name,
                    "date_deposited": inv.date_deposited.isoformat() if inv.date_deposited else None,
                }
                for inv in investments
            ]

            # Calculate current_stage (1-4) based on specific conditions
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if len(investments) > 0 else 0
            
            # Stage 2: Transferred - Marked complete ONLY when is_transferred is true
            if batch.is_transferred:
                current_stage = max(current_stage, 2)
            
            # Stage 3: Deployed - Marked complete ONLY if date_deployed is set AND deployment_confirmed is true
            if batch.date_deployed is not None and batch.deployment_confirmed:
                current_stage = max(current_stage, 3)
            
            # Stage 4: Active - Marked complete ONLY when is_active is true
            if batch.is_active:
                current_stage = max(current_stage, 4)

            # Determine status - Based on is_active field
            # Red "Deactivated" if is_active is false, Green "Active" if true
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": "Batch retrieved successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "total_principal": float(batch.total_principal) if batch.total_principal else 0,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if batch.date_deployed else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "investors_count": len(investments),
                    "is_active": batch.is_active,
                    "is_transferred": batch.is_transferred,
                    "deployment_confirmed": batch.deployment_confirmed,
                    "current_stage": current_stage,
                    "status": status,
                    "investments": investments_data,
                    "created_at": batch.date_created.isoformat() if hasattr(batch, 'date_created') else None
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch: {str(e)}"
            }), 500)

    @classmethod
    def get_all_batches(cls, session):
        """
        Get all batches with calculated fields.
        
        Args:
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batches = session.query(Batch).all()
            
            batch_list = []
            for batch in batches:
                # Base principal (deposits)
                total_deposits_sum = session.query(db.func.sum(Investment.amount_deposited)).filter(
                    Investment.batch_id == batch.id
                ).scalar() or 0.00

                # If epoch ledger exists, total_principal/total_capital should reflect latest ledger balances
                codes_subq = session.query(Investment.internal_client_code).filter(
                    Investment.batch_id == batch.id
                ).distinct().subquery()

                latest_per_key = session.query(
                    EpochLedger.internal_client_code.label("code"),
                    db.func.lower(EpochLedger.fund_name).label("fund"),
                    db.func.max(EpochLedger.epoch_end).label("max_end"),
                ).filter(
                    EpochLedger.internal_client_code.in_(select(codes_subq))
                ).group_by(
                    EpochLedger.internal_client_code,
                    db.func.lower(EpochLedger.fund_name),
                ).subquery()

                ledger_total = session.query(db.func.sum(EpochLedger.end_balance)).join(
                    latest_per_key,
                    (EpochLedger.internal_client_code == latest_per_key.c.code)
                    & (db.func.lower(EpochLedger.fund_name) == latest_per_key.c.fund)
                    & (EpochLedger.epoch_end == latest_per_key.c.max_end),
                    isouter=True,
                ).scalar()

                total_value = float(ledger_total) if ledger_total is not None else float(total_deposits_sum)
                
                # Count unique investors (by internal_client_code)
                investors_count = session.query(Investment).filter(
                    Investment.batch_id == batch.id
                ).count()
                
                # Determine status: 'Pending' if date_deployed is None, 'Active' otherwise
                status = 'Pending' if batch.date_deployed is None else 'Active'
                
                # Calculate fund-level breakdown for accurate filtering
                fund_rows = session.query(
                    CoreFund.fund_name.label("fund_name"),
                    db.func.coalesce(db.func.sum(Investment.amount_deposited), 0).label("total_principal"),
                    db.func.count(Investment.id).label("investors_count"),
                ).join(
                    CoreFund,
                    Investment.fund_id == CoreFund.id,
                ).filter(
                    Investment.batch_id == batch.id,
                ).group_by(
                    CoreFund.fund_name,
                ).all()

                fund_breakdown = [
                    {
                        "fund_name": fr.fund_name,
                        "total_principal": float(fr.total_principal),
                        "investors_count": int(fr.investors_count),
                    }
                    for fr in fund_rows
                ]

                batch_list.append({
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    # Dashboard should display latest ledger-based value when available
                    "total_principal": float(total_value),
                    "total_capital": float(total_value),
                    "funds": fund_breakdown,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if batch.date_deployed else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "investors_count": investors_count,
                    "is_active": batch.is_active,
                    "status": status
                })

            return make_response(jsonify({
                "status": 200,
                "message": "Batches retrieved successfully",
                "count": len(batch_list),
                "data": batch_list
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batches: {str(e)}"
            }), 500)

    @classmethod
    def update_batch(cls, batch_id, data, session):
        """
        Update a batch.
        
        Args:
            batch_id: ID of the batch
            data: dict with fields to update
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Update allowed fields
            if 'batch_name' in data:
                batch.batch_name = data['batch_name']
            if 'certificate_number' in data:
                batch.certificate_number = data['certificate_number']
            if 'date_deployed' in data:
                if data['date_deployed'] is not None:
                    batch.date_deployed = datetime.fromisoformat(data['date_deployed'])
                else:
                    batch.date_deployed = None
            if 'date_closed' in data:
                batch.date_closed = datetime.fromisoformat(data['date_closed'])
            if 'duration_days' in data:
                batch.duration_days = data['duration_days']
            if 'is_active' in data:
                batch.is_active = data['is_active']

            session.commit()

            # Determine status
            status = 'Pending' if batch.date_deployed is None else 'Active'

            return make_response(jsonify({
                "status": 200,
                "message": "Batch updated successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat() if batch.date_deployed else None,
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "is_active": batch.is_active,
                    "status": status
                }
            }), 200)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error updating batch: {str(e)}"
            }), 500)

    @classmethod
    def patch_batch(cls, batch_id, data, session):
        """
        Patch (partially update) a batch - for two-stage creation and status updates.
        Allows updating: batch_name, certificate_number, date_deployed, is_active, is_transferred
        
        Args:
            batch_id: ID of the batch
            data: dict with fields to update
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Update allowed fields for PATCH
            if 'batch_name' in data:
                batch.batch_name = data['batch_name']
            if 'certificate_number' in data:
                batch.certificate_number = data['certificate_number']
            if 'date_deployed' in data:
                if data['date_deployed'] is not None:
                    batch.date_deployed = datetime.fromisoformat(data['date_deployed'])
                else:
                    batch.date_deployed = None
            if 'is_active' in data:
                batch.is_active = data['is_active']
            if 'is_transferred' in data:
                batch.is_transferred = data['is_transferred']
            if 'deployment_confirmed' in data:
                batch.deployment_confirmed = data['deployment_confirmed']

            session.commit()

            # Determine status - Based on is_active field
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": "Batch patched successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat() if batch.date_deployed else None,
                    "is_active": batch.is_active,
                    "is_transferred": batch.is_transferred,
                    "deployment_confirmed": batch.deployment_confirmed,
                    "status": status
                }
            }), 200)

        except ValueError as e:
            return make_response(jsonify({
                "status": 400,
                "message": f"Invalid date format: {str(e)}"
            }), 400)
        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error patching batch: {str(e)}"
            }), 500)

    @classmethod
    def get_batch_with_investments(cls, batch_id, session):
        """
        Get a batch with all its investments.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
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
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "investor_email": inv.investor_email,
                    "investor_phone": inv.investor_phone,
                    "amount_deposited": float(inv.amount_deposited),
                    "date_deposited": inv.date_deposited.isoformat()
                }
                for inv in investments
            ]

            # Calculate total principal
            total_principal = sum(float(inv.amount_deposited) for inv in investments)

            return make_response(jsonify({
                "status": 200,
                "message": "Batch with investments retrieved successfully",
                "data": {
                    "id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "total_principal": total_principal,
                    "date_deployed": batch.date_deployed.isoformat(),
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat(),
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "investment_count": len(investments),
                    "investments": investments_data,
                    "is_active": batch.is_active
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch: {str(e)}"
            }), 500)

    @classmethod
    def get_batch_summary(cls, batch_id, session):
        """
        Get complete batch summary including investments and pro-rata distributions.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investments
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()

            # Get performance
            performance = session.query(Performance).filter(
                Performance.batch_id == batch_id
            ).first()

            # Get distributions
            distributions = session.query(ProRataDistribution).filter(
                ProRataDistribution.investment_id.in_(
                    session.query(Investment.id).filter(Investment.batch_id == batch_id)
                )
            ).all()

            total_invested = sum(float(inv.amount_deposited) for inv in investments)
            
            distributions_data = [
                {
                    "investor_name": d.investment.investor_name,
                    "investor_email": d.investment.investor_email,
                    "investor_phone": d.investment.investor_phone,
                    "amount_deposited": float(d.investment.amount_deposited),
                    "date_deposited": d.investment.date_deposited.isoformat(),
                    "days_active": d.days_active,
                    "weighted_capital": float(d.weighted_capital),
                    "profit_share_percentage": float(d.profit_share_percentage),
                    "profit_allocated": float(d.profit_allocated)
                }
                for d in distributions
            ]

            total_profit_allocated = sum(float(d.profit_allocated) for d in distributions) if distributions else 0

            return make_response(jsonify({
                "status": 200,
                "message": "Batch summary retrieved successfully",
                "data": {
                    "batch_id": batch.id,
                    "batch_name": batch.batch_name,
                    "certificate_number": batch.certificate_number,
                    "date_deployed": batch.date_deployed.isoformat(),
                    "duration_days": batch.duration_days,
                    "expected_close_date": batch.expected_close_date.isoformat(),
                    "date_closed": batch.date_closed.isoformat() if batch.date_closed else None,
                    "total_investors": len(investments),
                    "total_invested": total_invested,
                    "performance": {
                        "gross_profit": float(performance.gross_profit) if performance else None,
                        "transaction_costs": float(performance.transaction_costs) if performance else None,
                        "net_profit": float(performance.net_profit) if performance else None
                    } if performance else None,
                    "total_profit_allocated": total_profit_allocated,
                    "is_active": batch.is_active,
                    "distributions": distributions_data if distributions else []
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving batch summary: {str(e)}"
            }), 500)

    @classmethod
    def upload_batch_excel(cls, batch_id, file, session):
        """
        Upload and parse Excel file with investor data for a batch.
        
        Args:
            batch_id: ID of the batch
            file: The uploaded file object
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            import pandas as pd
            from io import BytesIO
            
            # Check if batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Batch with ID {batch_id} not found"
                }), 404)
            
            # Read file into DataFrame
            file_stream = BytesIO(file.read())
            
            # Try to read as Excel first, then CSV
            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file_stream)
                else:
                    df = pd.read_excel(file_stream)
            except Exception as e:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Error reading file: {str(e)}"
                }), 400)
            
            # Map column names (case-insensitive)
            column_mapping = {
                'client name': 'investor_name',
                'internal client code': 'internal_client_code',
                'amount(usd)': 'amount_deposited',
                'funds': 'fund_name',
            }
            
            # Normalize column names to lowercase
            df.columns = df.columns.str.lower().str.strip()
            
            # Rename columns according to mapping
            df = df.rename(columns=column_mapping)
            
            # Required columns
            required_columns = ['investor_name', 'internal_client_code', 'amount_deposited', 'fund_name']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"Missing required columns: {', '.join(missing_columns)}"
                }), 400)
            
            # Drop rows with missing values in required columns
            df = df.dropna(subset=required_columns)
            
            # Group by fund_name
            investments_added = 0
            total_amount = 0
            errors = []
            
            for fund_name, group in df.groupby('fund_name'):
                for idx, row in group.iterrows():
                    try:
                        investor_name = str(row['investor_name']).strip()
                        internal_client_code = str(row['internal_client_code']).strip()
                        amount_deposited = float(row['amount_deposited'])
                        
                        # Check for duplicate internal_client_code in this batch
                        existing = session.query(Investment).filter(
                            Investment.batch_id == batch_id,
                            Investment.internal_client_code == internal_client_code
                        ).first()
                        
                        if existing:
                            # Update existing investment
                            existing.investor_name = investor_name
                            existing.amount_deposited = amount_deposited
                        else:
                            # Create new investment
                            investment = Investment(
                                batch_id=batch_id,
                                investor_name=investor_name,
                                investor_email="",  # Can be updated later
                                investor_phone="",  # Can be updated later
                                internal_client_code=internal_client_code,
                                amount_deposited=amount_deposited,
                                fund_name=fund_name,
                                date_deposited=datetime.now()
                            )
                            session.add(investment)
                        
                        investments_added += 1
                        total_amount += amount_deposited
                        
                    except Exception as e:
                        errors.append(f"Row {idx}: {str(e)}")
            
            # Update batch total_principal
            batch.total_principal = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).with_entities(
                db.func.sum(Investment.amount_deposited)
            ).scalar() or 0
            
            session.commit()
            
            response_data = {
                "status": 201,
                "message": f"Successfully imported {investments_added} investors",
                "data": {
                    "batch_id": batch_id,
                    "batch_name": batch.batch_name,
                    "imported_investments": investments_added,
                    "total_amount": float(total_amount),
                    "investor_count": investments_added,
                }
            }
            
            if errors:
                response_data["warnings"] = errors
            
            return make_response(jsonify(response_data), 201)
            
        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error processing file: {str(e)}"
            }), 500)

    @classmethod
    def toggle_active(cls, batch_id, session):
        """
        Toggle the is_active status of a batch.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investment count for Stage 1 calculation
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()
            investors_count = len(investments)

            # Toggle is_active
            batch.is_active = not batch.is_active
            session.commit()

            # Calculate current_stage using 4-stage logic
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if investors_count > 0 else 0
            
            # Stage 2: Transferred - Marked complete ONLY when is_transferred is true
            if batch.is_transferred:
                current_stage = max(current_stage, 2)
            
            # Stage 3: Deployed - Marked complete ONLY if date_deployed is set AND deployment_confirmed is true
            if batch.date_deployed is not None and batch.deployment_confirmed:
                current_stage = max(current_stage, 3)
            
            # Stage 4: Active - Marked complete ONLY when is_active is true
            if batch.is_active:
                current_stage = max(current_stage, 4)

            # Determine status based on is_active
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": f"Batch is_active toggled to {batch.is_active}",
                "data": {
                    "id": batch.id,
                    "is_active": batch.is_active,
                    "current_stage": current_stage,
                    "status": status
                }
            }), 200)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error toggling batch active status: {str(e)}"
            }), 500)

    @classmethod
    def toggle_transferred(cls, batch_id, session):
        """
        Toggle the is_transferred status of a batch.
        
        Args:
            batch_id: ID of the batch
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get investment count for Stage 1 calculation
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id
            ).all()
            investors_count = len(investments)

            # Toggle is_transferred
            batch.is_transferred = not batch.is_transferred
            session.commit()

            # Calculate current_stage using 4-stage logic
            # Stage 1: Deposited - Marked complete ONLY if investors_count > 0
            current_stage = 1 if investors_count > 0 else 0
            
            # Stage 2: Transferred - Marked complete ONLY when is_transferred is true
            if batch.is_transferred:
                current_stage = max(current_stage, 2)
            
            # Stage 3: Deployed - Marked complete ONLY if date_deployed is set AND deployment_confirmed is true
            if batch.date_deployed is not None and batch.deployment_confirmed:
                current_stage = max(current_stage, 3)
            
            # Stage 4: Active - Marked complete ONLY when is_active is true
            if batch.is_active:
                current_stage = max(current_stage, 4)

            # Determine status based on is_active
            status = 'Active' if batch.is_active else 'Deactivated'

            return make_response(jsonify({
                "status": 200,
                "message": f"Batch is_transferred toggled to {batch.is_transferred}",
                "data": {
                    "id": batch.id,
                    "is_transferred": batch.is_transferred,
                    "current_stage": current_stage,
                    "status": status
                }
            }), 200)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error toggling batch transferred status: {str(e)}"
            }), 500)
