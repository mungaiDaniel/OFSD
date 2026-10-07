"""
Updated controllers to handle multi-fund batch operations.
This file complements the existing Batch/Investments/Performance controllers.
"""

from app.Batch.model import Batch
from app.Batch.fund import Fund, FundPerformance
from app.Investments.model import Investment
from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
from app.database.database import db
from app.logic.pro_rata_service import MultiFundProRataService
from app.utils.excel_handler import ExcelUploadHandler
from app.utils.email_service import EmailService
from app.utils.pdf_generator import generate_investor_statement_pdf
from flask import jsonify, make_response
from datetime import datetime, timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class FundController:
    """Controller for Fund operations within a Batch"""

    @classmethod
    def get_all_funds_for_batch(cls, batch_id, session):
        """Get all funds in a batch"""
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            funds = session.query(Fund).filter(Fund.batch_id == batch_id).all()

            if not funds:
                return make_response(jsonify({
                    "status": 404,
                    "message": "No funds found for this batch"
                }), 404)

            funds_data = []
            for fund in funds:
                funds_data.append({
                    "id": fund.id,
                    "fund_name": fund.fund_name,
                    "certificate_number": fund.certificate_number,
                    "total_capital": float(fund.total_capital),
                    "date_deployed": fund.date_deployed.isoformat(),
                    "expected_close_date": fund.expected_close_date.isoformat(),
                    "investor_count": len(fund.investments),
                    "is_active": fund.is_active
                })

            return make_response(jsonify({
                "status": 200,
                "message": "Funds retrieved successfully",
                "data": funds_data
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error retrieving funds: {str(e)}"
            }), 500)

    @classmethod
    def get_fund_summary(cls, batch_id, fund_name, session):
        """Get summary for a specific fund (detailed view)"""
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            fund = session.query(Fund).filter(
                Fund.batch_id == batch_id,
                Fund.fund_name == fund_name
            ).first()

            if not fund:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Fund {fund_name} not found"
                }), 404)

            # Get investments for this fund
            investments = session.query(Investment).filter(
                Investment.batch_id == batch_id,
                Investment.fund_name == fund_name
            ).all()

            # Get performance records
            performance_records = session.query(FundPerformance).filter(
                FundPerformance.fund_id == fund.id
            ).all()

            # Get distributions
            distributions = session.query(ProRataDistribution).filter(
                ProRataDistribution.fund_name == fund_name,
                ProRataDistribution.batch_id == batch_id
            ).all()

            investments_data = [
                {
                    "id": inv.id,
                    "investor_name": inv.investor_name,
                    "internal_client_code": inv.internal_client_code,
                    "amount_deposited": float(inv.amount_deposited),
                    "date_deposited": inv.date_deposited.isoformat()
                }
                for inv in investments
            ]

            performance_data = [
                {
                    "id": perf.id,
                    "report_date": perf.report_date.isoformat(),
                    "gross_profit": float(perf.gross_profit),
                    "transaction_costs": float(perf.transaction_costs),
                    "net_profit": float(perf.net_profit),
                    "cumulative_profit": float(perf.cumulative_profit)
                }
                for perf in performance_records
            ]

            distributions_data = [
                {
                    "investor_name": dist.investor_name,
                    "internal_client_code": dist.internal_client_code,
                    "days_active": dist.days_active,
                    "profit_share_percentage": float(dist.profit_share_percentage),
                    "profit_allocated": float(dist.profit_allocated)
                }
                for dist in distributions
            ]

            return make_response(jsonify({
                "status": 200,
                "message": "Fund summary retrieved",
                "data": {
                    "fund_name": fund.fund_name,
                    "total_capital": float(fund.total_capital),
                    "expected_close_date": fund.expected_close_date.isoformat(),
                    "investor_count": len(investments),
                    "investments": investments_data,
                    "performance_records": performance_data,
                    "distributions": distributions_data
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error: {str(e)}"
            }), 500)


class BatchFundPerformanceController:
    """Controller for fund-specific performance tracking"""

    @classmethod
    def create_fund_performance(cls, batch_id, fund_name, data, session):
        """
        Record monthly performance for a specific fund.
        
        Args:
            batch_id: Batch ID
            fund_name: Fund name (e.g., 'Axiom')
            data: dict with gross_profit, transaction_costs
        
        Returns:
            JSON response
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            fund = session.query(Fund).filter(
                Fund.batch_id == batch_id,
                Fund.fund_name == fund_name
            ).first()

            if not fund:
                return make_response(jsonify({
                    "status": 404,
                    "message": f"Fund {fund_name} not found"
                }), 404)

            # Create performance record
            gross_profit = Decimal(str(data.get('gross_profit', 0)))
            transaction_costs = Decimal(str(data.get('transaction_costs', 0)))

            # Calculate cumulative profit
            previous_performances = session.query(FundPerformance).filter(
                FundPerformance.fund_id == fund.id
            ).all()

            cumulative = Decimal('0.00')
            if previous_performances:
                cumulative = previous_performances[-1].cumulative_profit

            cumulative += (gross_profit - transaction_costs)

            fund_performance = FundPerformance(
                fund_id=fund.id,
                batch_id=batch_id,
                gross_profit=gross_profit,
                transaction_costs=transaction_costs,
                cumulative_profit=cumulative,
                report_date=datetime.now(timezone.utc),
                reporting_period=data.get('reporting_period', 'MONTHLY')
            )

            session.add(fund_performance)
            session.commit()

            return make_response(jsonify({
                "status": 201,
                "message": f"Performance recorded for fund {fund_name}",
                "data": {
                    "id": fund_performance.id,
                    "fund_name": fund_name,
                    "gross_profit": float(gross_profit),
                    "transaction_costs": float(transaction_costs),
                    "net_profit": float(fund_performance.net_profit),
                    "cumulative_profit": float(cumulative),
                    "report_date": fund_performance.report_date.isoformat()
                }
            }), 201)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error: {str(e)}"
            }), 500)


class ExcelUploadController:
    """Controller for Excel bulk uploads"""

    @classmethod
    def upload_investments_from_excel(cls, batch_id, file_path, session):
        """
        Upload investments from Excel file, auto-grouping by fund.
        
        Args:
            batch_id: Batch ID
            file_path: Path to Excel file
            session: Database session
        
        Returns:
            JSON response with upload summary
        """
        try:
            batch = session.query(Batch).filter(Batch.id == batch_id).first()
            if not batch:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Batch not found"
                }), 404)

            # Parse Excel
            success, excel_data, parse_message = ExcelUploadHandler.parse_excel_file(file_path)
            if not success:
                return make_response(jsonify({
                    "status": 400,
                    "message": parse_message
                }), 400)

            # Auto-assign funds if needed
            excel_data = ExcelUploadHandler.auto_assign_funds(excel_data)

            # Bulk upload
            success, created_count, message, fund_summary = ExcelUploadHandler.bulk_upload_investments(
                batch_id, excel_data, batch.date_deployed
            )

            if not success:
                return make_response(jsonify({
                    "status": 400,
                    "message": message
                }), 400)

            # Send Stage 1 Batch email asynchronously
            try:
                EmailService.send_deposit_received_batch(batch, excel_data)
            except Exception as email_err:
                logger.warning(f"Failed to trigger stage 1 batch emails: {email_err}")

            return make_response(jsonify({
                "status": 201,
                "message": message,
                "data": {
                    "created_count": created_count,
                    "funds": fund_summary
                }
            }), 201)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error: {str(e)}"
            }), 500)


class BatchLiveWeeklyController:
    """Controller for live weekly calculations"""

    @classmethod
    def get_weekly_update(cls, batch_id, fund_name, session):
        """
        Get live weekly update showing current accrued days and capital.
        
        Args:
            batch_id: Batch ID
            fund_name: Fund name
            session: Database session
        
        Returns:
            JSON response with weekly data
        """
        try:
            success, message, weekly_data = MultiFundProRataService.calculate_live_weekly_update(
                batch_id, fund_name
            )

            if not success:
                return make_response(jsonify({
                    "status": 404,
                    "message": message
                }), 404)

            return make_response(jsonify({
                "status": 200,
                "message": "Weekly update calculated",
                "data": {
                    "batch_id": weekly_data['batch_id'],
                    "fund_name": weekly_data['fund_name'],
                    "as_of_date": weekly_data['as_of_date'],
                    "total_capital": float(weekly_data['total_capital']),
                    "total_days_active": weekly_data['total_days_active'],
                    "investor_count": len(weekly_data['investors']),
                    "investors": weekly_data['investors']
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error: {str(e)}"
            }), 500)


class PDFReportController:
    """Controller for PDF generation"""

    @classmethod
    def generate_batch_pdf_report(cls, batch_id, output_path=None):
        """
        Generate PDF statement for a batch.
        
        Args:
            batch_id: Batch ID
            output_path: Optional output file path
        
        Returns:
            JSON response with PDF or file path
        """
        try:
            success, result = generate_investor_statement_pdf(batch_id, output_path)

            if not success:
                return make_response(jsonify({
                    "status": 500,
                    "message": result
                }), 500)

            return make_response(jsonify({
                "status": 200,
                "message": "PDF generated successfully",
                "data": {
                    "batch_id": batch_id,
                    "result": result
                }
            }), 200)

        except Exception as e:
            return make_response(jsonify({
                "status": 500,
                "message": f"Error: {str(e)}"
            }), 500)
