"""
Excel Bulk Upload Handler

This module handles uploading and parsing investment data from Excel files.
Excel format is expected to have columns:
- investor_name (String)
- investor_email (Email)
- internal_client_code (Unique ID from Excel - can appear in multiple batches)
- amount(usd) (Numeric with 2 decimals)
- fund (Fund name - 'Axiom', 'Atium', etc)
- date_transferred (datetime)

UPSERT Logic:
- An investor (internal_client_code) can exist in multiple different batches
- But can only appear once per batch
- If uploading same investor to same batch, the amount is updated
- If uploading same investor to different batch, a new record is created
"""

import openpyxl
from decimal import Decimal
from datetime import datetime
from app.Investments.model import Investment
from app.Batch.model import Batch
from app.Batch.fund import Fund
from app.Batch.core_fund import CoreFund
from app.database.database import db
from sqlalchemy import func
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
    # NOTE: Fund names are extracted from the uploaded Excel and are treated as global CoreFunds.
    # This avoids hardcoding 'Axiom' / 'Atium' and allows dynamic fund names.
    # Any missing fund names are assigned to a default bucket.

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
    def _normalize_fund_name(cls, value: str) -> str:
        """Normalize fund names for consistent storage and lookup."""
        if not value:
            return "Default"
        return str(value).strip().title()

    def bulk_upload_investments(cls, batch_id, excel_data, date_deployed):
        """Bulk upload investments from Excel data using upsert pattern.

        An investor (internal_client_code) can exist in multiple batches,
        but can only appear once per batch. If uploading the same investor
        code to the same batch, the amount is updated.

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

            # Normalize fund names and collect unique core funds
            for row in excel_data:
                row['fund'] = cls._normalize_fund_name(row.get('fund'))

            unique_funds = {row['fund'] for row in excel_data}

            # Ensure CoreFund records exist for each fund name (case-insensitive)
            existing_core_funds = {
                cf.fund_name.lower(): cf
                for cf in db.session.query(CoreFund)
                .filter(func.lower(CoreFund.fund_name).in_([f.lower() for f in unique_funds]))
                .all()
            }

            core_fund_map = {}
            for fund_name in unique_funds:
                fund_key = fund_name.lower()
                if fund_key in existing_core_funds:
                    core_fund_map[fund_name] = existing_core_funds[fund_key]
                else:
                    new_core = CoreFund(fund_name=fund_name, is_active=True)
                    db.session.add(new_core)
                    db.session.flush()  # ensure id is populated
                    core_fund_map[fund_name] = new_core

            # Group investments by fund name
            funds_data = {}
            for row in excel_data:
                fund_name = row.get('fund', 'Default')
                funds_data.setdefault(fund_name, []).append(row)

            # Create funds and investments
            created_count = 0
            updated_count = 0
            fund_summary = {}

            for fund_name, investments in funds_data.items():
                # Create or get batch-level fund record
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

                core_fund_id = core_fund_map.get(fund_name).id

                # Create investments with upsert logic
                fund_total_capital = Decimal('0.00')
                fund_investment_count = 0

                for inv_data in investments:
                    try:
                        amount = Decimal(str(inv_data.get('amount(usd)', 0)))
                        internal_client_code = inv_data.get('internal_client_code')

                        # UPSERT LOGIC: Search by internal_client_code AND batch_id
                        existing_investment = Investment.query.filter_by(
                            batch_id=batch_id,
                            internal_client_code=internal_client_code
                        ).first()

                        if existing_investment:
                            # Update existing investment in this batch
                            existing_investment.amount_deposited = amount
                            existing_investment.investor_name = inv_data.get('investor_name')
                            existing_investment.investor_email = inv_data.get('investor_email')
                            existing_investment.investor_phone = inv_data.get('investor_phone')
                            existing_investment.date_transferred = inv_data.get('date_transferred')
                            existing_investment.fund_name = fund_name
                            existing_investment.fund_id = core_fund_id

                            updated_count += 1
                            logger.info(f"Updated investment: {internal_client_code} in batch {batch_id}")
                        else:
                            # Create new investment
                            investment = Investment(
                                batch_id=batch_id,
                                fund_id=core_fund_id,
                                investor_name=inv_data.get('investor_name'),
                                investor_email=inv_data.get('investor_email'),
                                investor_phone=inv_data.get('investor_phone'),
                                internal_client_code=internal_client_code,
                                amount_deposited=amount,
                                date_deposited=inv_data.get('date_transferred', date_deployed),
                                date_transferred=inv_data.get('date_transferred'),
                                fund_name=fund_name
                            )
                            db.session.add(investment)
                            created_count += 1
                            logger.info(f"Created investment: {internal_client_code} in batch {batch_id}")

                        fund_investment_count += 1
                        fund_total_capital += amount

                    except Exception as e:
                        logger.warning(f"Error processing investment: {str(e)}")
                        # Rollback the transaction to clear any partial state
                        db.session.rollback()
                        return False, 0, f"Error processing investment: {str(e)}", {}

                # Update fund total capital
                fund.total_capital = fund_total_capital

                fund_summary[fund_name] = {
                    'fund_id': fund.id,
                    'investor_count': fund_investment_count,
                    'total_capital': float(fund_total_capital)
                }

            db.session.commit()

            # Build summary message
            summary_parts = []
            if created_count > 0:
                summary_parts.append(f"Created {created_count} investments")
            if updated_count > 0:
                summary_parts.append(f"Updated {updated_count} investments")

            message = ", ".join(summary_parts) if summary_parts else "No new investments"

            return True, created_count, message, fund_summary

        except Exception as e:
            logger.error(f"Error in bulk upload: {str(e)}", exc_info=True)
            # Rollback transaction to clear any partial state
            db.session.rollback()
            return False, 0, f"Error: {str(e)}", {}

    @classmethod
    def auto_assign_funds(cls, investments_data):
        """Ensure every row has a fund name.

        If the uploaded Excel omits the fund column, this will default to "Default".
        """
        for inv in investments_data:
            if 'fund' not in inv or not inv['fund']:
                inv['fund'] = 'Default'
            else:
                inv['fund'] = cls._normalize_fund_name(inv['fund'])

        return investments_data
