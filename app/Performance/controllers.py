from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.database.database import db
from app.logic.pro_rata_service import ProRataCalculationService
from flask import jsonify, make_response
from datetime import datetime
from decimal import Decimal


class PerformanceController:
    """Controller for Performance data and Pro-Rata calculations"""
    
    model = Performance

    @classmethod
    def create_performance(cls, data, session):
        """
        Create performance data for a specific fund within a batch.
        
        Args:
            data: dict with batch_id, fund_name, gross_profit, transaction_costs, date_closed (optional)
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            batch_id = data.get('batch_id')
            fund_name = data.get('fund_name', '').lower() if data.get('fund_name') else None
            
            # Validate batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Validate fund_name is provided
            if not fund_name:
                return make_response(jsonify({
                    "status": 400,
                    "message": "fund_name is required"
                }), 400)

            # Verify fund exists in batch (has investors)
            fund_exists = session.query(Investment).filter(
                Investment.batch_id == batch_id,
                Investment.fund_name == fund_name
            ).first()
            
            if not fund_exists:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"No investments found for fund '{fund_name}' in batch {batch_id}"
                }), 404)

            # Check if performance already exists for this fund
            existing = session.query(Performance).filter(
                Performance.batch_id == batch_id,
                Performance.fund_name == fund_name
            ).first()
            
            if existing:
                return make_response(jsonify({
                    "status": 409,
                    "message": f"Performance data already exists for fund '{fund_name}' in batch {batch_id}"
                }), 409)

            # Create performance record
            performance = cls.model(
                batch_id=batch_id,
                fund_name=fund_name,
                gross_profit=Decimal(str(data.get('gross_profit', 0))),
                transaction_costs=Decimal(str(data.get('transaction_costs', 0)))
            )

            performance.save(session)

            session.commit()

            return make_response(jsonify({
                "status": 201,
                "message": "Performance data created successfully",
                "data": {
                    "performance_id": performance.id,
                    "batch_id": performance.batch_id,
                    "fund_name": performance.fund_name,
                    "gross_profit": float(performance.gross_profit),
                    "transaction_costs": float(performance.transaction_costs),
                    "net_profit": float(performance.net_profit),
                    "date_created": performance.report_date.isoformat()
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
                "message": f"Error creating performance: {str(e)}"
            }), 500)

    @classmethod
    def calculate_pro_rata(cls, batch_id, fund_name, session):
        """
        Trigger pro-rata calculation for a specific fund in a batch.
        This MUST be called after performance data is entered for that fund.
        
        Args:
            batch_id: ID of the batch
            fund_name: Name of the fund (e.g., 'axiom', 'atium')
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            fund_name = fund_name.lower() if fund_name else None
            
            # Get batch
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get performance for this fund
            performance = session.query(Performance).filter(
                Performance.batch_id == batch_id,
                Performance.fund_name == fund_name
            ).first()
            
            if not performance:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Performance data not found for fund '{fund_name}' in batch {batch_id}. Please enter performance data first."
                }), 404)

            # Check if investments exist for this fund
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id,
                Investment.fund_name == fund_name
            ).all()
            
            if not investments:
                return make_response(jsonify({
                    "status": 400,
                    "message": f"No investments found for fund '{fund_name}' in batch {batch_id}"
                }), 400)

            # Delete old distributions for this fund/performance to avoid duplicates
            session.query(ProRataDistribution).filter(
                ProRataDistribution.performance_id == performance.id,
                ProRataDistribution.fund_name == fund_name
            ).delete()
            session.commit()

            # Perform fund-specific calculation
            success, message, distributions = ProRataCalculationService.calculate_fund_distributions(
                batch_id=batch_id,
                fund_name=fund_name,
                performance_id=performance.id
            )

            if not success:
                return make_response(jsonify({
                    "status": 400,
                    "message": message
                }), 400)

            # Save distributions to database
            for dist_data in distributions:
                dist_record = ProRataDistribution(
                    batch_id=batch_id,
                    fund_name=fund_name,
                    investment_id=dist_data['investment_id'],
                    performance_id=performance.id,
                    days_active=dist_data['days_active'],
                    weighted_capital=dist_data['weighted_capital'],
                    profit_share_percentage=dist_data['profit_share_percentage'],
                    profit_allocated=dist_data['profit_allocated'],
                    internal_client_code=dist_data.get('internal_client_code', ''),
                    investor_name=dist_data.get('investor_name', ''),
                    calculation_date=datetime.utcnow()
                )
                session.add(dist_record)
            
            session.commit()

            # Return summary
            total_allocated = sum(d['profit_allocated'] for d in distributions)
            
            return make_response(jsonify({
                "status": 200,
                "message": f"Pro-rata distributions calculated successfully (fund: {fund_name})",
                "data": [
                    {
                        "distribution_id": dist['investment_id'],  # Placeholder - actual ID from DB
                        "investment_id": dist['investment_id'],
                        "investor_name": dist['investor_name'],
                        "investor_email": dist['investor_email'],
                        "internal_client_code": dist.get('internal_client_code', ''),
                        "amount_deposited": float(dist['amount_deposited']),
                        "date_deposited": dist['date_deposited'].isoformat() if hasattr(dist['date_deposited'], 'isoformat') else str(dist['date_deposited']),
                        "days_active": dist['days_active'],
                        "weighted_capital": float(dist['weighted_capital']),
                        "profit_share_percentage": float(dist['profit_share_percentage']),
                        "profit_allocated": float(dist['profit_allocated']),
                        "calculation_date": datetime.utcnow().isoformat()
                    }
                    for dist in distributions
                ]
            }), 200)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error calculating pro-rata: {str(e)}"
            }), 500)

    @classmethod
    def get_performance_by_batch(cls, batch_id, session):
        """
        Get ALL performance data for a batch (supports multiple funds).
        
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

            # Get ALL performance records for this batch (one per fund)
            performances = session.query(Performance).filter(
                Performance.batch_id == batch_id
            ).all()
            
            if not performances:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Performance data not found for this batch"
                }), 404)

            # Return all performance records grouped by fund
            performance_data = [
                {
                    "performance_id": perf.id,
                    "batch_id": perf.batch_id,
                    "fund_name": perf.fund_name,
                    "gross_profit": float(perf.gross_profit),
                    "transaction_costs": float(perf.transaction_costs),
                    "net_profit": float(perf.net_profit),
                    "date_created": perf.report_date.isoformat() if perf.report_date else None
                }
                for perf in performances
            ]

            total_gross = sum(float(p['gross_profit']) for p in performance_data)
            total_costs = sum(float(p['transaction_costs']) for p in performance_data)
            total_net = sum(float(p['net_profit']) for p in performance_data)

            return make_response(jsonify({
                "status": 200,
                "message": "Performance data retrieved successfully",
                "batch_id": batch_id,
                "batch_name": batch.batch_name,
                "count": len(performance_data),
                "data": performance_data,
                "summary": {
                    "total_gross_profit": total_gross,
                    "total_transaction_costs": total_costs,
                    "total_net_profit": total_net,
                    "funds_count": len(performance_data)
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving performance: {str(e)}"
            }), 500)

    @classmethod
    def get_performance_by_fund(cls, batch_id, fund_name, session):
        """
        Get performance data for a specific fund in a batch.
        
        Args:
            batch_id: ID of the batch
            fund_name: Name of the fund
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            fund_name = fund_name.lower() if fund_name else None
            
            # Validate batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get performance for this specific fund
            performance = session.query(Performance).filter(
                Performance.batch_id == batch_id,
                Performance.fund_name == fund_name
            ).first()
            
            if not performance:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Performance data not found for fund '{fund_name}' in batch {batch_id}"
                }), 404)

            return make_response(jsonify({
                "status": 200,
                "message": "Performance data retrieved successfully",
                "batch_id": batch_id,
                "batch_name": batch.batch_name,
                "data": {
                    "performance_id": performance.id,
                    "batch_id": performance.batch_id,
                    "fund_name": performance.fund_name,
                    "gross_profit": float(performance.gross_profit),
                    "transaction_costs": float(performance.transaction_costs),
                    "net_profit": float(performance.net_profit),
                    "date_created": performance.report_date.isoformat() if performance.report_date else None
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving performance: {str(e)}"
            }), 500)
        """
        Get all pro-rata distributions for a batch (across all funds).
        
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

            # Get all distributions for this batch
            distributions = session.query(ProRataDistribution).filter(
                ProRataDistribution.batch_id == batch_id
            ).all()

            if not distributions:
                return make_response(jsonify({
                    "status": 404,
                    "message": "No distributions found. Run pro-rata calculation first."
                }), 404)

            # Group by fund
            funds_data = {}
            for dist in distributions:
                fund_name = dist.fund_name or 'default'
                if fund_name not in funds_data:
                    funds_data[fund_name] = []
                
                funds_data[fund_name].append({
                    "distribution_id": dist.id,
                    "investment_id": dist.investment_id,
                    "investor_name": dist.investor_name,
                    "investor_email": dist.investment.investor_email if dist.investment else '',
                    "internal_client_code": dist.internal_client_code,
                    "amount_deposited": float(dist.investment.amount_deposited) if dist.investment else 0,
                    "date_deposited": dist.investment.date_deposited.isoformat() if dist.investment else '',
                    "days_active": dist.days_active,
                    "weighted_capital": float(dist.weighted_capital),
                    "profit_share_percentage": float(dist.profit_share_percentage),
                    "profit_allocated": float(dist.profit_allocated)
                })

            # Calculate summary stats
            summary_stats = {}
            total_allocated = Decimal('0.00')
            for fund_name, distributions_list in funds_data.items():
                fund_total = sum(d['profit_allocated'] for d in distributions_list)
                summary_stats[fund_name] = {
                    'investor_count': len(distributions_list),
                    'total_allocated': fund_total
                }
                total_allocated += Decimal(str(fund_total))

            return make_response(jsonify({
                "status": 200,
                "message": "Distributions retrieved successfully",
                "batch_id": batch_id,
                "batch_name": batch.batch_name,
                "total_distributed": float(total_allocated),
                "funds": funds_data,
                "summary": summary_stats
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving distributions: {str(e)}"
            }), 500)

    @classmethod
    def get_distributions_by_fund(cls, batch_id, fund_name, session):
        """
        Get pro-rata distributions for a specific fund in a batch.
        
        Args:
            batch_id: ID of the batch
            fund_name: Name of the fund
            session: database session
        
        Returns:
            tuple: (json_response, status_code)
        """
        try:
            fund_name = fund_name.lower() if fund_name else None
            
            # Validate batch exists
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Get distributions for this fund
            distributions = session.query(ProRataDistribution).filter(
                ProRataDistribution.batch_id == batch_id,
                ProRataDistribution.fund_name == fund_name
            ).all()

            if not distributions:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"No distributions found for fund '{fund_name}' in batch {batch_id}"
                }), 404)

            distributions_data = [
                {
                    "distribution_id": dist.id,
                    "investment_id": dist.investment_id,
                    "investor_name": dist.investor_name,
                    "investor_email": dist.investment.investor_email if dist.investment else '',
                    "internal_client_code": dist.internal_client_code,
                    "amount_deposited": float(dist.investment.amount_deposited) if dist.investment else 0,
                    "date_deposited": dist.investment.date_deposited.isoformat() if dist.investment else '',
                    "days_active": dist.days_active,
                    "weighted_capital": float(dist.weighted_capital),
                    "profit_share_percentage": float(dist.profit_share_percentage),
                    "profit_allocated": float(dist.profit_allocated),
                    "calculation_date": dist.calculation_date.isoformat() if dist.calculation_date else ''
                }
                for dist in distributions
            ]

            total_allocated = sum(d['profit_allocated'] for d in distributions_data)

            return make_response(jsonify({
                "status": 200,
                "message": "Fund distributions retrieved successfully",
                "fund_name": fund_name,
                "batch_id": batch_id,
                "batch_name": batch.batch_name,
                "total_allocated": total_allocated,
                "investor_count": len(distributions_data),
                "data": distributions_data,
                "summary": {
                    "fund": fund_name,
                    "total_investors": len(distributions_data),
                    "total_allocated": total_allocated,
                    "average_profit_per_investor": total_allocated / len(distributions_data) if distributions_data else 0
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving fund distributions: {str(e)}"
            }), 500)
