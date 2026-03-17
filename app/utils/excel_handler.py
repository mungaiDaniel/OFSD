"""
Excel Bulk Upload Handler

This module handles uploading and parsing investment data from Excel files.
Excel format is expected to have columns:
- investor_name (String)
- investor_email (Email)
- internal_client_code (Unique ID)
- amount(usd) (Numeric with 2 decimals)
- fund (Fund name - 'Axiom', 'Atium', etc)
- date_transferred (datetime)
"""

import openpyxl
from decimal import Decimal
from datetime import datetime
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.Batch.fund import Fund
from app.database.database import db
import logging

logger = logging.getLogger(__name__)


class ExcelUploadHandler:
    """Handle Excel file uploads for bulk investment import"""

    # Expected Excel columns
    REQUIRED_COLUMNS = {
        'investor_name': str,
        'investor_email': str,
        'internal_client_code': str,
        'amount(usd)': Decimal,
        'fund': str,
        'date_transferred': datetime
    }

    # Fund grouping rules
    FUND_INVESTOR_MAPPING = {
        'Axiom': list(range(1, 8)),      # Investors 1-7
        'Atium': list(range(8, 13))      # Investors 8-12
    }

    @classmethod
    def parse_excel_file(cls, file_path):
        """
        Parse Excel file and extract investment data.
        
        Args:
            file_path: Path to Excel file
        
        Returns:
            tuple: (success: bool, data: list[dict], message: str)
        """
        try:
            workbook = openpyxl.load_workbook(file_path)
            worksheet = workbook.active

            # Get headers (first row)
            headers = []
            for cell in worksheet[1]:
                headers.append(cell.value)

            if not headers:
                return False, [], "Excel file is empty"

            # Parse data rows
            data = []
            for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, values_only=False), start=2):
                row_data = {}
                for col_idx, cell in enumerate(row):
                    header = headers[col_idx] if col_idx < len(headers) else None
                    if header:
                        row_data[header] = cell.value

                if cls._validate_row(row_data):
                    data.append(row_data)
                else:
                    logger.warning(f"Skipping invalid row {row_idx}: {row_data}")

            return True, data, f"Successfully parsed {len(data)} records"

        except Exception as e:
            logger.error(f"Error parsing Excel file: {str(e)}", exc_info=True)
            return False, [], f"Error parsing file: {str(e)}"

    @classmethod
    def _validate_row(cls, row_data):
        """Validate a single row of data"""
        required_fields = ['investor_name', 'investor_email', 'internal_client_code', 'amount(usd)', 'fund']
        return all(field in row_data and row_data[field] is not None for field in required_fields)

    @classmethod
    def bulk_upload_investments(cls, batch_id, excel_data, date_deployed):
        """
        Bulk upload investments from Excel data.
        
        Args:
            batch_id: ID of the batch
            excel_data: List of dicts from parsed Excel
            date_deployed: Deployment date of the batch
        
        Returns:
            tuple: (success: bool, created_count: int, message: str, fund_summary: dict)
        """
        try:
            batch = Batch.query.get(batch_id)
            if not batch:
                return False, 0, "Batch not found", {}

            # Group by fund
            funds_data = {}
            for row in excel_data:
                fund_name = row.get('fund', 'Default')
                if fund_name not in funds_data:
                    funds_data[fund_name] = []
                funds_data[fund_name].append(row)

            # Create funds and investments
            created_count = 0
            fund_summary = {}

            for fund_name, investments in funds_data.items():
                # Create or get fund
                fund = Fund.query.filter_by(
                    batch_id=batch_id,
                    fund_name=fund_name
                ).first()

                if not fund:
                    fund = Fund(
                        batch_id=batch_id,
                        fund_name=fund_name,
                        certificate_number=batch.certificate_number,
                        date_deployed=batch.date_deployed,
                        duration_days=batch.duration_days
                    )
                    db.session.add(fund)
                    db.session.flush()

                # Create investments
                fund_total_capital = Decimal('0.00')
                fund_investment_count = 0

                for inv_data in investments:
                    try:
                        amount = Decimal(str(inv_data.get('amount(usd)', 0)))
                        
                        investment = Investment(
                            batch_id=batch_id,
                            fund_id=fund.id,
                            investor_name=inv_data.get('investor_name'),
                            investor_email=inv_data.get('investor_email'),
                            investor_phone=inv_data.get('investor_phone'),
                            internal_client_code=inv_data.get('internal_client_code'),
                            amount_deposited=amount,
                            date_deposited=inv_data.get('date_transferred', date_deployed),
                            date_transferred=inv_data.get('date_transferred'),
                            fund_name=fund_name
                        )
                        db.session.add(investment)
                        created_count += 1
                        fund_investment_count += 1
                        fund_total_capital += amount

                    except Exception as e:
                        logger.warning(f"Error creating investment: {str(e)}")
                        continue

                # Update fund total capital
                fund.total_capital = fund_total_capital
                
                fund_summary[fund_name] = {
                    'fund_id': fund.id,
                    'investor_count': fund_investment_count,
                    'total_capital': float(fund_total_capital)
                }

            db.session.commit()
            return True, created_count, f"Successfully created {created_count} investments", fund_summary

        except Exception as e:
            logger.error(f"Error in bulk upload: {str(e)}", exc_info=True)
            db.session.rollback()
            return False, 0, f"Error: {str(e)}", {}

    @classmethod
    def auto_assign_funds(cls, investments_data):
        """
        Auto-assign fund names based on investor order if not specified.
        
        Args:
            investments_data: List of investment dicts
        
        Returns:
            List of dicts with fund names assigned
        """
        for idx, inv in enumerate(investments_data, start=1):
            if 'fund' not in inv or not inv['fund']:
                # Assign based on investor number
                if idx <= 7:
                    inv['fund'] = 'Axiom'
                else:
                    inv['fund'] = 'Atium'

        return investments_data
