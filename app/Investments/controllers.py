from app.Investments.model import Investment, PendingEmail, EmailLog
from app.Batch.model import Batch
from app.database.database import db
from flask import jsonify, make_response
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from app.Batch.core_fund import CoreFund
from app.Batch.fund import Fund
from app.utils.email_service import EmailService
from app.logic.batch_management_service import BatchManagementService
from app.Funds.share_class import ShareClass


class InvestmentController:
    """Controller for Investment operations"""
    
    model = Investment

    @staticmethod
    def _q4(value):
        return Decimal(str(value)).quantize(Decimal("0.0001"))

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
            # 1. Resolve Fund and Share Class
            fund_id = data.get('fund_id')
            fund_name = (data.get('fund_name') or '').strip()
            core = None
            if fund_id is not None:
                core = session.query(CoreFund).filter(CoreFund.id == int(fund_id)).first()
            elif fund_name:
                fund_name_normalized = fund_name.title()
                core = session.query(CoreFund).filter(db.func.lower(CoreFund.fund_name) == fund_name_normalized.lower()).first()

            if not core:
                return make_response(jsonify({"status": 400, "message": "Valid core fund (fund_id or fund_name) is required for auto-batching"}), 400)

            # Find the primary active share class for this fund
            share_class = session.query(ShareClass).filter(ShareClass.core_fund_id == core.id, ShareClass.is_active == True).first()
            if not share_class:
                 return make_response(jsonify({"status": 400, "message": f"No active share class found for fund: {core.fund_name}"}), 400)

            # 2. Resolve or Create Batch (Auto-Batching)
            batch_id = data.get('batch_id')
            if not batch_id:
                # Use Auto-Batching Service
                batch = BatchManagementService.find_or_create_batch(share_class.id)
                batch_id = batch.id
            else:
                # Validate provided batch exists
                batch = session.query(Batch).filter(Batch.id == batch_id).first()
                if not batch:
                    return make_response(jsonify({"status": 404, "message": "Batch not found"}), 404)

            # fund is optional; resolve only when fund_id or fund_name provided
            resolved_fund_id = core.id
            resolved_fund_name = core.fund_name

            # Create new investment with optional fund assignment
            amount_deposited = Decimal(str(data.get('amount_deposited', 0)))
            share_series = (data.get("share_series") or resolved_fund_name or fund_name or "").strip() or None
            currency_type = data.get("currency_type") or Investment.currency_from_share_series(share_series)
            shares_owned = data.get("shares_owned")
            investment = cls.model(
                investor_name=data.get('investor_name'),
                investor_email=data.get('investor_email', ''),
                investor_phone=data.get('investor_phone', ''),
                amount_deposited=amount_deposited,
                date_deposited=datetime.fromisoformat(data.get('date_deposited', datetime.now(timezone.utc).isoformat())),
                batch_id=batch_id,
                fund_id=resolved_fund_id,
                fund_name=resolved_fund_name,
                internal_client_code=data.get('internal_client_code'),
                wealth_manager=data.get('wealth_manager'),
                IFA=data.get('IFA'),
                contract_note=data.get('contract_note'),
                valuation=Decimal(str(data['valuation'])) if data.get('valuation') else None,
                date_transferred=datetime.fromisoformat(data['date_transferred']) if data.get('date_transferred') else None
            )
            investment.share_series = share_series
            investment.currency_type = currency_type
            investment.original_deposit_amount = amount_deposited
            investment.current_market_value = Decimal("0.00")
            if shares_owned is not None:
                investment.shares_owned = cls._q4(shares_owned)

            investment.save(session)

            # Trigger Stage 1 deposit email for this specific deposit unless explicitly disabled.
            if data.get("send_email", True):
                try:
                    EmailService.send_batch_stage_emails(
                        batch,
                        1,
                        investments=[{
                            "investor_id": investment.id,
                            "investor_email": investment.investor_email,
                            "investor_name": investment.investor_name,
                            "amount_deposited": float(investment.amount_deposited or 0),
                            "currency_type": investment.currency_type,
                        }],
                        trigger_source="investor_add",
                    )
                except Exception:
                    # Do not fail investor creation if notification enqueue fails.
                    pass

            return make_response(jsonify({
                "status": 201,
                "message": "Investment added successfully",
                "id": investment.id,
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
                "id": investment.id,
                "investor_name": investment.investor_name,
                "investor_email": investment.investor_email,
                "investor_phone": investment.investor_phone,
                "internal_client_code": investment.internal_client_code,
                "amount_deposited": float(investment.amount_deposited),
                "date_deposited": investment.date_deposited.isoformat(),
                "fund_name": investment.fund_name,
                "batch_id": investment.batch_id,
                "wealth_manager": investment.wealth_manager,
                "IFA": investment.IFA,
                "contract_note": investment.contract_note,
                "valuation": float(investment.valuation) if investment.valuation else None,
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
                "investments": investments_data,
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
            if 'wealth_manager' in data:
                investment.wealth_manager = data['wealth_manager']
            if 'IFA' in data:
                investment.IFA = data['IFA']
            if 'contract_note' in data:
                investment.contract_note = data['contract_note']
            if 'valuation' in data:
                investment.valuation = Decimal(str(data['valuation'])) if data['valuation'] is not None else None
            
            # Handle shares_owned update with automatic opening_market_value recalculation
            if 'shares_owned' in data and data['shares_owned'] is not None:
                investment.shares_owned = cls._q4(data['shares_owned'])
                # Auto-recalculate opening_market_value if previous_nav_price is available
                if investment.previous_nav_price:
                    investment.opening_market_value = investment.shares_owned * investment.previous_nav_price
            
            if 'previous_nav_price' in data:
                investment.previous_nav_price = Decimal(str(data['previous_nav_price'])) if data['previous_nav_price'] is not None else None
                # If updating NAV price and shares_owned exists, recalculate opening_market_value
                if investment.shares_owned and investment.previous_nav_price:
                    investment.opening_market_value = investment.shares_owned * investment.previous_nav_price
            
            if 'opening_market_value' in data:
                investment.opening_market_value = Decimal(str(data['opening_market_value'])) if data['opening_market_value'] is not None else None

            session.commit()

            if investment.batch_id is not None:
                from app.Batch.controllers import BatchController
                BatchController.refresh_cached_total_capital(investment.batch_id, session)

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
                    "batch_id": investment.batch_id,
                    "shares_owned": float(investment.shares_owned) if investment.shares_owned else None,
                    "previous_nav_price": float(investment.previous_nav_price) if investment.previous_nav_price else None,
                    "opening_market_value": float(investment.opening_market_value) if investment.opening_market_value else None
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
    def delete_investment(cls, investment_id, session, actor_user=None):
        """
        Permanently delete one investment (deposit) row — super-admin-only
        destructive action, triggered from the batch "Show all" investor
        list. Mirrors the cleanup BatchController.delete_batch does for a
        whole batch, scoped to this single investment: several tables FK to
        investments.id WITHOUT ondelete=CASCADE (pending_emails, email_logs,
        statements, report_recipients, investment_batch_valuations,
        pro_rata_distribution) and would raise a FK violation on a bare
        session.delete() once any of those rows exist for this investor.
        investor_shares.investment_id IS ondelete=CASCADE at the DB level,
        but it's still deleted explicitly here rather than relied upon, for
        the same reason delete_batch does: production schema drift in this
        app has a history of not matching what the models declare.

        Args:
            investment_id: ID of the investment
            session: database session
            actor_user: the super_admin User performing the delete (for the audit log)

        Returns:
            tuple: (json_response, status_code)
        """
        from app.Valuation.model import Statement, InvestmentBatchValuation
        from app.Reports.model import ReportRecipient, ReportRun
        from app.Performance.pro_rata_distribution import ProRataDistribution
        from app.Funds.investor_shares import InvestorShares
        from app.Batch.controllers import BatchController
        from app.utils.audit_log import create_audit_log

        try:
            investment = session.query(Investment).filter(Investment.id == investment_id).first()

            if not investment:
                return make_response(jsonify({
                    "status": 404,
                    "message": "Investment not found"
                }), 404)

            snapshot = {
                "investor_name": investment.investor_name,
                "internal_client_code": investment.internal_client_code,
                "batch_id": investment.batch_id,
                "fund_id": investment.fund_id,
                "amount_deposited": float(investment.amount_deposited) if investment.amount_deposited is not None else None,
                "shares_owned": float(investment.shares_owned) if investment.shares_owned else None,
            }
            batch_id = investment.batch_id

            session.query(PendingEmail).filter(PendingEmail.investor_id == investment_id).delete(synchronize_session=False)
            session.query(EmailLog).filter(EmailLog.investor_id == investment_id).delete(synchronize_session=False)
            session.query(Statement).filter(Statement.investor_id == investment_id).delete(synchronize_session=False)

            touched_run_ids = [
                rid for (rid,) in session.query(ReportRecipient.report_run_id)
                .filter(ReportRecipient.investor_id == investment_id)
                .distinct()
                .all()
            ]
            session.query(ReportRecipient).filter(ReportRecipient.investor_id == investment_id).delete(synchronize_session=False)
            for run_id in touched_run_ids:
                remaining = session.query(ReportRecipient.id).filter(ReportRecipient.report_run_id == run_id).first()
                if not remaining:
                    session.query(ReportRun).filter(ReportRun.id == run_id).delete(synchronize_session=False)

            session.query(InvestmentBatchValuation).filter(InvestmentBatchValuation.investment_id == investment_id).delete(synchronize_session=False)
            session.query(ProRataDistribution).filter(ProRataDistribution.investment_id == investment_id).delete(synchronize_session=False)
            session.query(InvestorShares).filter(InvestorShares.investment_id == investment_id).delete(synchronize_session=False)

            session.delete(investment)
            session.commit()

            if batch_id is not None:
                BatchController.refresh_cached_total_capital(batch_id, session, commit=True)

            create_audit_log(
                action="DELETE_INVESTMENT",
                target_type="investment",
                target_id=investment_id,
                target_name=snapshot["investor_name"],
                description=f"Deleted investment {investment_id} ({snapshot['internal_client_code']}) from batch {batch_id}",
                old_value=snapshot,
                actor_user_id=getattr(actor_user, "id", None),
                actor_user_email=getattr(actor_user, "email", None),
                actor_user_name=getattr(actor_user, "name", None),
            )

            return make_response('', 204)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({
                "status": 500,
                "message": f"Error deleting investment: {str(e)}"
            }), 500)

    @classmethod
    def create_new_investor(cls, data, session):
        """
        Create a new investor with auto-batch assignment (NAV-based).
        """
        try:
            # Validate share_class exists and belongs to fund
            share_class = session.query(ShareClass).filter(
                ShareClass.id == data['share_class_id'],
                ShareClass.core_fund_id == data['fund_id'],
                ShareClass.is_active == True
            ).first()
            if not share_class:
                return make_response(jsonify({"status": 400, "message": "Invalid share_class_id for the specified fund"}), 400)

            # Get fund details
            fund = session.query(CoreFund).filter(CoreFund.id == data['fund_id']).first()
            if not fund:
                return make_response(jsonify({"status": 400, "message": "Fund not found"}), 400)

            # Use BatchManagementService for auto-batching
            batch = BatchManagementService.find_or_create_batch(data['share_class_id'])

            # Create investment
            investment = cls.model(
                investor_name=data['investor_name'],
                investor_email=data['investor_email'],
                investor_phone=data.get('investor_phone'),
                internal_client_code=data['internal_client_code'],
                amount_deposited=Decimal(str(data['deposit_amount'])),
                date_deposited=datetime.fromisoformat(data['deposit_date']),
                batch_id=batch.id,
                fund_id=data['fund_id'],
                fund_name=fund.fund_name,
                share_class_id=data['share_class_id'],
                deposit_date=datetime.fromisoformat(data['deposit_date']).date(),
                original_deposit_amount=Decimal(str(data['deposit_amount'])),
                current_market_value=Decimal("0.00"),
                currency_type=data.get('currency_type') or share_class.currency  # Set currency from frontend or share_class
            )

            investment.save(session)

            # Trigger Stage 1 deposit email for this top-up deposit unless explicitly disabled.
            if data.get("send_email", True):
                try:
                    EmailService.send_batch_stage_emails(
                        batch,
                        1,
                        investments=[{
                            "investor_id": investment.id,
                            "investor_email": investment.investor_email,
                            "investor_name": investment.investor_name,
                            "amount_deposited": float(investment.amount_deposited or 0),
                            "currency_type": investment.currency_type,  # Pass the currency to email
                        }],
                        trigger_source="investor_add",
                    )
                except Exception:
                    # Do not fail investor creation if notification enqueue fails.
                    pass

            return make_response(jsonify({
                "status": 201,
                "data": {
                    "investment_id": investment.id,
                    "batch_id": batch.id,
                    "batch_name": batch.batch_name,
                    "fund_name": fund.fund_name,
                    "class_code": share_class.class_code,
                    "currency": share_class.currency,
                    "deposit_amount": float(investment.amount_deposited),
                    "batch_close_at": batch.auto_close_at.isoformat() if batch.auto_close_at else None,
                    "batch_close_at": batch.auto_close_at.isoformat() if batch.auto_close_at else None
                }
            }), 201)

        except IntegrityError:
            session.rollback()
            existing = session.query(Investment).filter(
                db.func.lower(Investment.internal_client_code) == db.func.lower(data.get("internal_client_code", ""))
            ).first()
            if existing:
                return make_response(jsonify({"status": 409, "message": "Investor with this client code already exists"}), 409)
            return make_response(jsonify({
                "status": 409,
                "message": "Could not create investor due to a batch naming conflict. Please retry."
            }), 409)
        except Exception as e:
            session.rollback()
            return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

    @classmethod
    def add_existing_investor_deposit(cls, data, session):
        """
        Add a new deposit for an existing investor (NAV-based).
        """
        try:
            # Find existing investor by client_code
            existing_investment = session.query(Investment).filter(
                Investment.internal_client_code == data['internal_client_code']
            ).first()
            if not existing_investment:
                return make_response(jsonify({"status": 404, "message": "Investor not found"}), 404)

            # Validate share_class exists and belongs to fund
            share_class = session.query(ShareClass).filter(
                ShareClass.id == data['share_class_id'],
                ShareClass.core_fund_id == data['fund_id'],
                ShareClass.is_active == True
            ).first()
            if not share_class:
                return make_response(jsonify({"status": 400, "message": "Invalid share_class_id for the specified fund"}), 400)

            # Get fund details
            fund = session.query(CoreFund).filter(CoreFund.id == data['fund_id']).first()
            if not fund:
                return make_response(jsonify({"status": 400, "message": "Fund not found"}), 400)

            # Use BatchManagementService for auto-batching
            batch = BatchManagementService.find_or_create_batch(data['share_class_id'])

            # Create new investment record for this deposit
            investment = cls.model(
                investor_name=existing_investment.investor_name,
                investor_email=existing_investment.investor_email,
                investor_phone=existing_investment.investor_phone,
                internal_client_code=data['internal_client_code'],
                amount_deposited=Decimal(str(data['deposit_amount'])),
                date_deposited=datetime.fromisoformat(data['deposit_date']),
                batch_id=batch.id,
                fund_id=data['fund_id'],
                fund_name=fund.fund_name,
                share_class_id=data['share_class_id'],
                deposit_date=datetime.fromisoformat(data['deposit_date']).date(),
                original_deposit_amount=Decimal(str(data['deposit_amount'])),
                current_market_value=Decimal("0.00"),
                currency_type=data.get('currency_type') or share_class.currency  # Set currency from frontend or share_class
            )

            investment.save(session)

            # Trigger Stage 1 deposit email for this top-up deposit unless explicitly disabled.
            if data.get("send_email", True):
                try:
                    EmailService.send_batch_stage_emails(
                        batch,
                        1,
                        investments=[{
                            "investor_id": investment.id,
                            "investor_email": investment.investor_email,
                            "investor_name": investment.investor_name,
                            "amount_deposited": float(investment.amount_deposited or 0),
                            "currency_type": investment.currency_type,  # Pass the currency to email
                        }],
                        trigger_source="investor_add",
                    )
                except Exception:
                    # Do not fail investor creation if notification enqueue fails.
                    pass

            return make_response(jsonify({
                "status": 201,
                "data": {
                    "investment_id": investment.id,
                    "batch_id": batch.id,
                    "batch_name": batch.batch_name,
                    "fund_name": fund.fund_name,
                    "class_code": share_class.class_code,
                    "currency": share_class.currency,
                    "deposit_amount": float(investment.amount_deposited)
                }
            }), 201)

        except Exception as e:
            session.rollback()
            return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

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

            # Resolve global batch only if provided (legacy/override)
            global_batch = None
            if batch_id:
                global_batch = session.query(Batch).filter(Batch.id == batch_id).first()
                if not global_batch:
                    return make_response(jsonify({
                        "status": 404,
                        "message": f"Global batch with ID {batch_id} not found"
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
                'amount': 'amount_deposited',
                'funds': 'fund_name',
                'fund': 'fund_name',
                'date_deposited': 'date_deposited',
                'date_transferred': 'date_transferred',
                'wealth_manager': 'wealth_manager',
                'ifa': 'IFA',
                'contract_note': 'contract_note',
                'valuation': 'valuation',
                'investor_email': 'investor_email',
                'investor_phone': 'investor_phone'
                , 'share_series': 'share_series'
                , 'share series': 'share_series'
                , 'shares_owned': 'shares_owned'
                , 'shares owned': 'shares_owned'
                , 'currency': 'currency_type'
                , 'currency_type': 'currency_type'
            }
            df = df.rename(columns=column_mapping)

            required_columns = ['investor_name', 'investor_email', 'internal_client_code', 'amount_deposited', 'fund_name']
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
            touched_batch_ids = set()

            for idx, row in df.iterrows():
                try:
                    investor_name = str(row['investor_name']).strip()
                    internal_client_code = str(row['internal_client_code']).strip()
                    amount_deposited = float(row['amount_deposited'])
                    share_series_val = str(row.get('share_series')).strip() if 'share_series' in row and row.get('share_series') is not None and not pd.isna(row.get('share_series')) else ""
                    shares_owned_val = row.get('shares_owned') if 'shares_owned' in row else None
                    currency_type_val = str(row.get('currency_type')).strip().upper() if 'currency_type' in row and row.get('currency_type') is not None and not pd.isna(row.get('currency_type')) else None
                    fund_name_raw = str(row['fund_name']).strip()

                    investor_email = str(row['investor_email']).strip() if 'investor_email' in row and not pd.isna(row['investor_email']) else ''
                    investor_phone = str(row['investor_phone']).strip() if 'investor_phone' in row and not pd.isna(row['investor_phone']) else ''

                    # get_or_create fund and share class logic
                    normalized_fund_name = str(fund_name_raw).strip().title()
                    if not normalized_fund_name:
                        raise ValueError('fund_name cannot be empty')

                    if normalized_fund_name not in core_cache:
                        core_fund = session.query(CoreFund).filter(db.func.lower(CoreFund.fund_name) == normalized_fund_name.lower()).first()
                        if not core_fund:
                            core_fund = CoreFund(fund_name=normalized_fund_name, is_active=True)
                            session.add(core_fund)
                            session.flush()
                        
                        share_class = session.query(ShareClass).filter(ShareClass.core_fund_id == core_fund.id, ShareClass.is_active == True).first()
                        core_cache[normalized_fund_name] = (core_fund, share_class)
                    
                    core_fund, share_class = core_cache[normalized_fund_name]

                    # Auto-Batching Logic: Find or create the correct batch for this share class
                    target_batch = None
                    if share_class:
                        target_batch = BatchManagementService.find_or_create_batch(share_class.id)
                    elif global_batch:
                        target_batch = global_batch
                    else:
                        raise ValueError(f"No active share class found for fund '{normalized_fund_name}' and no global batch provided.")
                    touched_batch_ids.add(target_batch.id)

                    # Upsert: check for existing (internal_client_code, batch_id)
                    existing = session.query(Investment).filter(
                        Investment.batch_id == target_batch.id,
                        Investment.internal_client_code == internal_client_code
                    ).first()

                    # Per-batch Fund (Legacy detailed tracking)
                    batch_fund = session.query(Fund).filter_by(batch_id=target_batch.id, fund_name=normalized_fund_name).first()
                    if not batch_fund:
                        batch_fund = Fund(
                            batch_id=target_batch.id,
                            fund_name=normalized_fund_name,
                            certificate_number=target_batch.certificate_number or f"AUTO-{target_batch.id}-{normalized_fund_name}",
                            date_deployed=target_batch.date_deployed or datetime.utcnow(),
                            duration_days=target_batch.duration_days or 30,
                            total_capital=0
                        )
                        session.add(batch_fund)
                        session.flush()

                    if existing:
                        # Update existing investment in this batch
                        existing.investor_name = investor_name
                        existing.investor_email = investor_email
                        existing.investor_phone = investor_phone
                        existing.amount_deposited = Decimal(str(amount_deposited))
                        existing.fund_name = normalized_fund_name
                        existing.fund_id = core_fund.id
                        existing.share_class_id = share_class.id if share_class else None
                        existing.share_series = share_series_val or existing.share_series or batch_fund.fund_name
                        existing.currency_type = currency_type_val if currency_type_val in ("USD", "KES") else Investment.currency_from_share_series(existing.share_series)
                        existing.original_deposit_amount = Decimal(str(amount_deposited))
                        existing.current_market_value = Decimal("0.00")
                        if shares_owned_val is not None and not pd.isna(shares_owned_val):
                            existing.shares_owned = cls._q4(shares_owned_val)
                        
                        # Safe date_deposited handling
                        if 'date_deposited' in row and row['date_deposited'] is not None and not pd.isna(row['date_deposited']):
                            try:
                                existing.date_deposited = pd.to_datetime(row['date_deposited'])
                            except:
                                existing.date_deposited = target_batch.date_deployed or datetime.utcnow()
                        else:
                            existing.date_deposited = target_batch.date_deployed or datetime.utcnow()
                        
                        # Optional fields
                        existing.wealth_manager = row.get('wealth_manager') if 'wealth_manager' in row and not pd.isna(row.get('wealth_manager')) else None
                        existing.IFA = row.get('IFA') if 'IFA' in row and not pd.isna(row.get('IFA')) else None
                        existing.contract_note = row.get('contract_note') if 'contract_note' in row and not pd.isna(row.get('contract_note')) else None
                        
                        # Safe valuation conversion
                        if 'valuation' in row and row['valuation'] is not None and not pd.isna(row['valuation']):
                            try:
                                existing.valuation = Decimal(str(float(row['valuation'])))
                            except:
                                existing.valuation = None
                    else:
                        # Safe date_deposited for new investment
                        date_dep = target_batch.date_deployed or datetime.utcnow()
                        if 'date_deposited' in row and row['date_deposited'] is not None and not pd.isna(row['date_deposited']):
                            try:
                                date_dep = pd.to_datetime(row['date_deposited'])
                            except:
                                pass
                        
                        # Safe valuation for new investment
                        val = None
                        if 'valuation' in row and row['valuation'] is not None and not pd.isna(row['valuation']):
                            try:
                                val = Decimal(str(float(row['valuation'])))
                            except:
                                pass
                        
                        # Insert new row
                        investment = Investment(
                            batch_id=target_batch.id,
                            investor_name=investor_name,
                            investor_email=investor_email,
                            investor_phone=investor_phone,
                            internal_client_code=internal_client_code,
                            amount_deposited=Decimal(str(amount_deposited)),
                            fund_name=normalized_fund_name,
                            fund_id=core_fund.id,
                            share_class_id=share_class.id if share_class else None,
                            date_deposited=date_dep,
                            wealth_manager=row.get('wealth_manager') if 'wealth_manager' in row and not pd.isna(row.get('wealth_manager')) else None,
                            IFA=row.get('IFA') if 'IFA' in row and not pd.isna(row.get('IFA')) else None,
                            contract_note=row.get('contract_note') if 'contract_note' in row and not pd.isna(row.get('contract_note')) else None,
                            valuation=val
                        )
                        investment.share_series = share_series_val or batch_fund.fund_name
                        investment.currency_type = currency_type_val if currency_type_val in ("USD", "KES") else Investment.currency_from_share_series(investment.share_series)
                        investment.original_deposit_amount = Decimal(str(amount_deposited))
                        investment.current_market_value = Decimal("0.00")
                        if shares_owned_val is not None and not pd.isna(shares_owned_val):
                            investment.shares_owned = cls._q4(shares_owned_val)
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
                    "message": "A duplicate investor record was detected. This usually means two rows share the same Internal Client Code in the same batch.",
                    "error": {
                        "type": "UniqueViolation",
                        "detail": str(getattr(ie, "orig", ie))
                    }
                }), 409)

            session.commit()

            if touched_batch_ids:
                from app.Batch.controllers import BatchController
                BatchController.refresh_cached_total_capital_for_batch_ids(touched_batch_ids, session)

            # Stage A: move progress to Deposited and email all investors in batch
            email_stats = {'sent': 0, 'failed': 0}
            try:
                email_stats = EmailService.send_batch_stage_emails(batch, 1, [
                    {
                        'investor_email': str(row['investor_email']).strip(),
                        'investor_name': str(row['investor_name']).strip(),
                        'amount_deposited': float(row['amount_deposited']),
                        'currency_type': str(row.get('currency_type')).strip().upper() if row.get('currency_type') is not None and not pd.isna(row.get('currency_type')) else 'USD',
                        'date_deposited': row.get('date_deposited', batch.date_deployed or datetime.utcnow())
                    }
                    for _, row in df.iterrows()
                ], trigger_source="investment.upload.stage_1_initial_deposit")
                print(f"Email sent to {email_stats['sent']} addresses, failed {email_stats['failed']}")

            except Exception as e:
                # Do not abort; log only.
                print(f"Email Stage 1 dispatch failed: {e}")

            response_data = {
                "status": 201,
                "message": f"Successfully imported {investments_processed} investor(s) into batch '{batch.batch_name}'",
                "data": {
                    "batch_id": batch_id,
                    "batch_name": batch.batch_name,
                    "imported_count": investments_processed,
                    "total_amount": float(total_amount),
                    "emails_sent": email_stats.get('sent', 0),
                    "emails_failed": email_stats.get('failed', 0)
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
