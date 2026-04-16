from flask import current_app
from flask_mail import Mail, Message
import logging
from datetime import datetime
import threading

from app.database.database import db
from app.Investments.model import EmailLog, Investment, PendingEmail
from sqlalchemy.orm import scoped_session, sessionmaker

logger = logging.getLogger(__name__)

mail = Mail()

class EmailService:
    """Unified Service for status-driven investor notifications (Stages 1-3)."""

    BCC_EMAIL = "invest@aib-axysafrica.com"

    @staticmethod
    def init_app(app):
        mail.init_app(app)

    @classmethod
    def _create_pending_email(cls, batch_id, investor_id, email_type, subject, body, recipient_email, recipient_name=None, amount=None, fund_name=None, batch_name=None, trigger_source=None):
        """Create a pending email record for manual approval."""
        try:
            pending_email = PendingEmail(
                batch_id=batch_id,
                investor_id=investor_id,
                email_type=email_type,
                subject=subject,
                body=body,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                amount=amount,
                fund_name=fund_name,
                batch_name=batch_name,
                status='Pending_Confirmation',
                trigger_source=trigger_source,
            )
            db.session.add(pending_email)
            db.session.commit()
            logger.info(f"Created pending email for {recipient_email} ({email_type})")
            return pending_email
        except Exception as e:
            logger.error(f"Failed to create pending email: {str(e)}")
            db.session.rollback()
            return None

    @classmethod
    def _bcc_email(cls) -> str:
        return current_app.config.get("MAIL_BCC", cls.BCC_EMAIL)

    @classmethod
    def _send_email_immediately(cls, subject, body, recipient_email, recipient_name=None):
        """Send email immediately without approval."""
        try:
            bcc_email = cls._bcc_email()
            msg = Message(
                subject=subject,
                recipients=[recipient_email],
                bcc=[bcc_email],
                body=body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER', bcc_email)
            )
            mail.send(msg)
            logger.info(f"Email sent immediately to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
            return False

    @classmethod
    def send_deposit_received_batch(cls, batch, investments, trigger_source=None):
        """
        Stage 1: Deposit Received (Excel Upload Complete).
        Triggered when a batch of rows is processed.

        IMPORTANT: We extract all data from SQLAlchemy objects before spawning the thread.
        The background thread must never access SQLAlchemy ORM objects directly.
        """
        app = current_app._get_current_object()

        # Extract batch data BEFORE entering the thread (session is still alive here)
        batch_name = getattr(batch, 'batch_name', 'Unknown Batch')
        batch_id = getattr(batch, 'id', None)

        # Serialize investments to plain dicts right now, while session is open
        email_items = []
        for inv in investments:
            if isinstance(inv, dict):
                email_items.append({
                    'investor_email': inv.get('investor_email'),
                    'investor_name': inv.get('investor_name') or inv.get('name'),
                    'amount_deposited': inv.get('amount_deposited', 0),
                })
            else:
                email_items.append({
                    'investor_email': getattr(inv, 'investor_email', None),
                    'investor_name': getattr(inv, 'investor_name', None),
                    'amount_deposited': float(getattr(inv, 'amount_deposited', 0) or 0),
                })

        def process_emails():
            with app.app_context():
                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)
                logger.info(f"Processing {len(email_items)} Stage 1 emails for batch '{batch_name}' (manual_approval={manual_approval})")
                
                if manual_approval:
                    # Create pending emails for manual approval
                    created = 0
                    for item in email_items:
                        email = item['investor_email']
                        name = item['investor_name']
                        amount = item['amount_deposited']

                        if not email:
                            logger.warning(f"Skipping investor '{name}' — no email address")
                            continue

                        subject = f"Deposit Received - {batch_name}"
                        body = f"""Dear {name},

We have successfully received your investment deposit. 

Batch: {batch_name}
Capital Amount: USD {float(amount):,.2f}
Status: Deposited (Stage 1/3)

Your funds are now being held securely while we finalize the batch for offshore transfer. You will be notified once the transfer is initiated.

Best regards,
AIB-AXYS Africa Investment Team

"""
                        # Find investor_id if possible
                        investor_id = None
                        if not isinstance(investments[0], dict):
                            # Find the matching investment object
                            for inv in investments:
                                if getattr(inv, 'investor_email', None) == email:
                                    investor_id = getattr(inv, 'id', None)
                                    break

                        cls._create_pending_email(
                            batch_id=batch_id,
                            investor_id=investor_id,
                            email_type='DEPOSIT_CONFIRMATION',
                            subject=subject,
                            body=body,
                            recipient_email=email,
                            recipient_name=name,
                            amount=amount,
                            batch_name=batch_name,
                            trigger_source=trigger_source,
                        )
                        created += 1
                    logger.info(f"Created {created} pending emails for batch '{batch_name}'")
                else:
                    # Send emails immediately
                    sent, failed = 0, 0
                    for item in email_items:
                        try:
                            email = item['investor_email']
                            name = item['investor_name']
                            amount = item['amount_deposited']

                            if not email:
                                logger.warning(f"Skipping investor '{name}' — no email address")
                                cls._log_email_event(investor_email=email, batch_id=batch_id, status='Failed', email_type='DEPOSIT_CONFIRMATION', error_message='Missing email')
                                failed += 1
                                continue

                            subject = f"Deposit Received - {batch_name}"
                            body = f"""Dear {name},

We have successfully received your investment deposit. 

Batch: {batch_name}
Capital Amount: USD {float(amount):,.2f}
Status: Deposited (Stage 1/3)

Your funds are now being held securely while we finalize the batch for offshore transfer. You will be notified once the transfer is initiated.

Best regards,
AIB-AXYS Africa Investment Team

"""
                            if cls._send_email_immediately(subject, body, email, name):
                                sent += 1
                                cls._log_email_event(investor_email=email, batch_id=batch_id, status='Sent', email_type='DEPOSIT_CONFIRMATION')
                            else:
                                failed += 1
                                cls._log_email_event(investor_email=email, batch_id=batch_id, status='Failed', email_type='DEPOSIT_CONFIRMATION', error_message='Send failed')
                        except Exception as e:
                            failed += 1
                            logger.error(f"Stage 1 email failed: {str(e)}")
                            cls._log_email_event(investor_email=email if 'email' in locals() else None, batch_id=batch_id, status='Failed', email_type='DEPOSIT_CONFIRMATION', error_message=str(e))
                    
                    logger.info(f"Stage 1 batch complete for '{batch_name}': {sent} sent, {failed} failed")
                    
                    # Log summary record for audit trail
                    unique_investors = len([i for i in email_items if i.get('investor_email')])
                    cls._log_email_summary(
                        batch_id=batch_id,
                        email_type='DEPOSIT_CONFIRMATION',
                        recipient_count=unique_investors,
                        success_count=sent,
                        failure_count=failed,
                    )

        threading.Thread(target=process_emails, daemon=True).start()

    @classmethod
    def _log_email_event(cls, *, investor_email=None, investor_id=None, batch_id=None, status='Failed', email_type=None, recipient_count=None, success_count=None, failure_count=None, error_message=None, retry_count=0, trigger_source=None):
        try:
            # Create a new session for the thread
            Session = scoped_session(sessionmaker(bind=db.engine))
            session = Session()

            if investor_id is None and investor_email:
                inv = session.query(Investment).filter(Investment.investor_email.ilike(investor_email.strip())).first()
                investor_id = inv.id if inv else None

            row = EmailLog(
                investor_id=investor_id,
                batch_id=batch_id,
                status=status,
                email_type=email_type,
                recipient_count=recipient_count,
                success_count=success_count,
                failure_count=failure_count,
                error_message=error_message[:512] if error_message else None,
                retry_count=retry_count,
                trigger_source=trigger_source,
            )
            session.add(row)
            session.commit()
            session.close()
        except Exception as e:
            logger.warning(f"Failed to log email event: {str(e)}")

    @classmethod
    def _log_email_summary(cls, batch_id, email_type, recipient_count, success_count, failure_count):
        """Store one summary record for a batch stage email event."""
        try:
            cls._log_email_event(
                investor_email=None,
                investor_id=None,
                batch_id=batch_id,
                status='Summary',
                email_type=email_type,
                recipient_count=recipient_count,
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as e:
            logger.warning(f"Failed to log summary email event: {str(e)}")

    @classmethod
    def _send_email_batch(cls, batch_name, email_items, batch_id=None):
        """Synchronous dispatch for email lists, used by send_batch_stage_emails."""
        sent, failed = 0, 0
        for item in email_items:
            investor_id = item.get('investor_id')
            investor_email = item.get('investor_email')
            try:
                email = investor_email
                name = item.get('investor_name', 'Investor')
                amount = item.get('amount_deposited', 0)

                if not email:
                    logger.warning(f"Skipping investor '{name}' — no email address")
                    failed += 1
                    cls._log_email_event(investor_email=investor_email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='DEPOSIT_CONFIRMATION', error_message='Missing email')
                    continue

                subject = f"Deposit Received - {batch_name}"
                body = f"""Dear {name},\n\nWe have successfully received your investment deposit. \n\nBatch: {batch_name}\nCapital Amount: USD {float(amount):,.2f}\nStatus: Deposited (Stage 1/3)\n\nYour funds are now being held securely while we finalize the batch for offshore transfer. You will be notified once the transfer is initiated.\n\nBest regards,\nAIB-AXYS Africa Investment Team\n\n"""

                msg = Message(
                    subject=subject,
                    recipients=[email],
                    bcc=[cls._bcc_email()],
                    body=body,
                    sender=current_app.config.get('MAIL_DEFAULT_SENDER', cls._bcc_email())
                )
                mail.send(msg)
                sent += 1
                cls._log_email_event(investor_email=investor_email, investor_id=investor_id, batch_id=batch_id, status='Sent', email_type='DEPOSIT_CONFIRMATION')
            except Exception as e:
                failed += 1
                cls._log_email_event(investor_email=investor_email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='DEPOSIT_CONFIRMATION', error_message=str(e))
                logger.error(f"Stage 1 batch email failed for {item}: {str(e)}")

        # Track unique investors by ID and email (for edge cases with duplicates)
        unique_investors = {
            item.get('investor_id') or item.get('investor_email')
            for item in email_items
            if item.get('investor_email')
        }
        recipient_count = len(unique_investors)

        # Summary row per stage for timeline/recent activity
        cls._log_email_summary(
            batch_id=batch_id,
            email_type='DEPOSIT_CONFIRMATION',
            recipient_count=recipient_count,
            success_count=sent,
            failure_count=failed,
        )

        return {'sent': sent, 'failed': failed}

    @classmethod
    def send_batch_stage_emails(cls, batch, stage, investments=None, trigger_source=None):
        """API used by batch controllers to trigger stage emails."""
        if stage == 1:
            if investments is None:
                # fallback: use existing batch investments with light extraction
                investments = [
                    {
                        'investor_email': getattr(inv, 'investor_email', None),
                        'investor_name': getattr(inv, 'investor_name', None),
                        'amount_deposited': getattr(inv, 'amount_deposited', 0)
                    }
                    for inv in getattr(batch, 'investments', [])
                ]
            cls.send_deposit_received_batch(batch, investments, trigger_source=trigger_source)
            queued = len([item for item in investments if item.get('investor_email')])
            return {'sent': 0, 'failed': 0, 'queued': queued}

        if stage == 2:
            cls.send_offshore_transfer_batch(batch, trigger_source=trigger_source)
            return {'sent': 0, 'failed': 0}

        if stage in (3, 4):
            cls.send_investment_active_batch(batch, trigger_source=trigger_source)
            return {'sent': 0, 'failed': 0}

        logger.warning(f"Unsupported stage for email dispatch: {stage}")
        return {'sent': 0, 'failed': 0}

    @classmethod
    def send_offshore_transfer_batch(cls, batch, trigger_source=None):
        """
        Stage 2: Offshore Fund Transfer.
        Triggered when 'Mark as Transferred' is checked in UI.
        """
        app = current_app._get_current_object()

        # Extract core batch data BEFORE the thread starts
        batch_name = getattr(batch, 'batch_name', 'Unknown Batch')
        batch_id = getattr(batch, 'id', None)

        def process_emails():
            with app.app_context():
                from app.Investments.model import Investment

                investments = db.session.query(Investment).filter(
                    Investment.batch_id == batch_id
                ).all()

                email_items = [
                    {
                        'investor_id': getattr(inv, 'id', None),
                        'investor_name': getattr(inv, 'investor_name', None),
                        'investor_email': getattr(inv, 'investor_email', None),
                        'amount_deposited': float(getattr(inv, 'amount_deposited', 0)),
                        'transfer_fee_deducted': float(getattr(inv, 'transfer_fee_deducted', 0)),
                        'deployment_fee_deducted': float(getattr(inv, 'deployment_fee_deducted', 0)),
                        'net_principal': float(getattr(inv, 'net_principal', 0)),
                    }
                    for inv in investments
                ]
                batch_total_principal = sum(item.get('amount_deposited', 0) for item in email_items)
                batch_total_net = sum(item.get('net_principal', 0) for item in email_items)

                unique_recipients = {
                    item.get('investor_id') or item.get('investor_email')
                    for item in email_items
                    if item.get('investor_email')
                }

                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)
                logger.info(f"Processing Stage 2 emails for batch '{batch_name}' (manual_approval={manual_approval})")
                
                if manual_approval:
                    # Create pending emails for manual approval
                    created = 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        
                        if not email:
                            logger.warning(f"Skipping investor '{name}' — no email address")
                            continue
                        principal = float(item.get('amount_deposited', 0) or 0)
                        transaction_fee = float(item.get('transfer_fee_deducted', 0) or 0)
                        entry_fee = float(item.get('deployment_fee_deducted', 0) or 0)
                        net = float(item.get('net_principal', 0) or 0)
                        weight_pct = ((principal / batch_total_principal) * 100) if batch_total_principal > 0 else 0.0
                            
                        subject = f"Funds Successfully Transferred to Fund - {batch_name}"
                        body = f"""Dear {name},

We are pleased to inform you that your funds in batch "{batch_name}" have been successfully transferred to our offshore investment partner.

Status: Transferred (Stage 2/3)

The funds are now awaiting final deployment into the active portfolio. We will notify you once the deployment is confirmed and your returns begin to accrue.

Initial Deposit: ${principal:,.2f}
Batch Total Deployed: ${batch_total_net:,.2f}
Your Contribution Weight: {weight_pct:.4f}%
Allocated Transaction Fee: -${transaction_fee:,.2f}
Allocated Entry Fee: -${entry_fee:,.2f}
New Active Balance: ${net:,.2f}

Best regards,
AIB-AXYS Africa Investment Team

"""
                        cls._create_pending_email(
                            batch_id=batch_id,
                            investor_id=investor_id,
                            email_type='OFFSHORE_TRANSFER',
                            subject=subject,
                            body=body,
                            recipient_email=email,
                            recipient_name=name,
                            batch_name=batch_name
                        )
                        created += 1
                    logger.info(f"Created {created} pending emails for batch '{batch_name}'")
                else:
                    # Send emails immediately
                    sent, failed = 0, 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        if not email:
                            cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='OFFSHORE_TRANSFER', error_message='Missing email')
                            failed += 1
                            continue
                        principal = float(item.get('amount_deposited', 0) or 0)
                        transaction_fee = float(item.get('transfer_fee_deducted', 0) or 0)
                        entry_fee = float(item.get('deployment_fee_deducted', 0) or 0)
                        net = float(item.get('net_principal', 0) or 0)
                        weight_pct = ((principal / batch_total_principal) * 100) if batch_total_principal > 0 else 0.0
                        try:
                            subject = f"Funds Successfully Transferred to Fund - {batch_name}"
                            body = f"""Dear {name},

We are pleased to inform you that your funds in batch "{batch_name}" have been successfully transferred to our offshore investment partner.

Status: Transferred (Stage 2/3)

The funds are now awaiting final deployment into the active portfolio. We will notify you once the deployment is confirmed and your returns begin to accrue.

Initial Deposit: ${principal:,.2f}
Batch Total Deployed: ${batch_total_net:,.2f}
Your Contribution Weight: {weight_pct:.4f}%
Allocated Transaction Fee: -${transaction_fee:,.2f}
Allocated Entry Fee: -${entry_fee:,.2f}
New Active Balance: ${net:,.2f}

Best regards,
AIB-AXYS Africa Investment Team

"""
                            if cls._send_email_immediately(subject, body, email, name):
                                sent += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Sent', email_type='OFFSHORE_TRANSFER')
                                logger.info(f"Stage 2 email sent to {email}")
                            else:
                                failed += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='OFFSHORE_TRANSFER', error_message='Send failed')
                        except Exception as e:
                            failed += 1
                            cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='OFFSHORE_TRANSFER', error_message=str(e))
                            logger.error(f"Stage 2 email failed for {email}: {str(e)}")
                    
                    cls._log_email_summary(
                        batch_id=batch_id,
                        email_type='OFFSHORE_TRANSFER',
                        recipient_count=len(unique_recipients),
                        success_count=sent,
                        failure_count=failed,
                    )
                    logger.info(f"Stage 2 batch complete for '{batch_name}': {sent} sent, {failed} failed")

        threading.Thread(target=process_emails, daemon=True).start()

    @classmethod
    def send_investment_active_batch(cls, batch, trigger_source=None):
        """
        Stage 3: Investment Active (Deployed).
        Triggered when 'Confirm Deployment' is checked or Date Deployed is saved.
        Includes transaction cost breakdown in the email.
        """
        app = current_app._get_current_object()

        # Extract all data from ORM objects BEFORE the thread starts
        batch_name = getattr(batch, 'batch_name', 'Unknown Batch')
        batch_id = getattr(batch, 'id', None)
        deploy_date = (
            batch.date_deployed.strftime('%Y-%m-%d')
            if getattr(batch, 'date_deployed', None)
            else datetime.now().strftime('%Y-%m-%d')
        )
        transaction_cost = float(getattr(batch, 'transaction_cost', 0) or 0)
        
        email_items = [
            {
                'investor_id': getattr(inv, 'id', None),
                'investor_name': getattr(inv, 'investor_name', None),
                'investor_email': getattr(inv, 'investor_email', None),
                'amount_deposited': float(getattr(inv, 'amount_deposited', 0) or 0),
                'deployment_fee_deducted': float(getattr(inv, 'deployment_fee_deducted', 0) or 0),
            }
            for inv in getattr(batch, 'investments', [])
        ]

        unique_recipients = {
            item.get('investor_id') or item.get('investor_email')
            for item in email_items
            if item.get('investor_email')
        }

        def process_emails():
            with app.app_context():
                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)
                logger.info(f"Processing Stage 3 emails for batch '{batch_name}' (manual_approval={manual_approval})")
                
                if manual_approval:
                    # Create pending emails for manual approval
                    created = 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        original_amount = item.get('amount_deposited', 0)
                        fee_deducted = item.get('deployment_fee_deducted', 0)
                        net_amount = original_amount - fee_deducted
                        
                        if not email:
                            logger.warning(f"Skipping investor '{name}' — no email address")
                            continue
                        
                        # Build subject and body with transaction cost details
                        subject = f"Funds Successfully Deployed: {batch_name}"
                        
                        fee_line = ""
                        if fee_deducted > 0:
                            fee_line = f"""
Transaction Fee Contribution: -${fee_deducted:,.2f}
Net Deployed Amount: ${net_amount:,.2f}"""
                        
                        body = f"""Dear {name},

Congratulations! Your investment in {batch_name} has been successfully deployed and is now ACTIVE.

═══════════════════════════════════════════
DEPLOYMENT SUMMARY
═══════════════════════════════════════════

Original Deposit Amount: ${original_amount:,.2f}{fee_line}

Deployment Date: {deploy_date}
Status: Active (Stage 3/3)

Your capital is now earning returns based on the fund's performance. You can track your real-time performance and view upcoming reports through the investor portal.

═══════════════════════════════════════════

Thank you for investing with AIB-AXYS Africa.

Best regards,
AIB-AXYS Africa Investment Team

"""
                        cls._create_pending_email(
                            batch_id=batch_id,
                            investor_id=investor_id,
                            email_type='INVESTMENT_ACTIVE',
                            subject=subject,
                            body=body,
                            recipient_email=email,
                            recipient_name=name,
                            batch_name=batch_name
                        )
                        created += 1
                    logger.info(f"Created {created} pending emails for batch '{batch_name}'")
                else:
                    # Send emails immediately
                    sent, failed = 0, 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        original_amount = item.get('amount_deposited', 0)
                        fee_deducted = item.get('deployment_fee_deducted', 0)
                        net_amount = original_amount - fee_deducted
                        
                        if not email:
                            cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', error_message='Missing email')
                            failed += 1
                            continue
                        try:
                            subject = f"Funds Successfully Deployed: {batch_name}"
                            
                            fee_line = ""
                            if fee_deducted > 0:
                                fee_line = f"""
Transaction Fee Contribution: -${fee_deducted:,.2f}
Net Deployed Amount: ${net_amount:,.2f}"""
                            
                            body = f"""Dear {name},

Congratulations! Your investment in {batch_name} has been successfully deployed and is now ACTIVE.

═══════════════════════════════════════════
DEPLOYMENT SUMMARY
═══════════════════════════════════════════

Original Deposit Amount: ${original_amount:,.2f}{fee_line}

Deployment Date: {deploy_date}
Status: Active (Stage 3/3)

Your capital is now earning returns based on the fund's performance. You can track your real-time performance and view upcoming reports through the investor portal.

═══════════════════════════════════════════

Thank you for investing with AIB-AXYS Africa.

Best regards,
AIB-AXYS Africa Investment Team

"""
                            if cls._send_email_immediately(subject, body, email, name):
                                sent += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Sent', email_type='INVESTMENT_ACTIVE')
                                logger.info(f"Stage 3 email sent to {email}")
                            else:
                                failed += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='INVESTMENT_ACTIVE', error_message='Send failed')
                        except Exception as e:
                            failed += 1
                            cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='INVESTMENT_ACTIVE', error_message=str(e))
                            logger.error(f"Stage 3 email failed for {email}: {str(e)}")
                    
                    cls._log_email_summary(
                        batch_id=batch_id,
                        email_type='INVESTMENT_ACTIVE',
                        recipient_count=len(unique_recipients),
                        success_count=sent,
                        failure_count=failed,
                    )
                    logger.info(f"Stage 3 batch complete for '{batch_name}': {sent} sent, {failed} failed")

        threading.Thread(target=process_emails, daemon=True).start()

    @classmethod
    def send_withdrawal_received_email(cls, client_code, investor_name, investor_email, amount, fund_name, trigger_source=None):
        """Notification: Withdrawal request received (Stage 1 Withdrawal)."""
        app = current_app._get_current_object()
        
        def process_email():
            with app.app_context():
                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)
                logger.info(f"Processing withdrawal received email for {investor_email} (manual_approval={manual_approval})")
                
                try:
                    if not investor_email:
                        return
                    
                    subject = f"Withdrawal Request Received - {fund_name}"
                    body = f"""Dear {investor_name},

This is to confirm that we have received your withdrawal request for your investment in {fund_name}.

Client Code: {client_code}
Withdrawal Amount: USD {float(amount):,.2f}
Status: Received / Processing

Our team is currently reviewing your request. You will receive a follow-up notification once the withdrawal is approved and scheduled for distribution.

Best regards,
AIB-AXYS Africa Investment Team

"""
                    if manual_approval:
                        # Find investor_id if possible
                        investor_id = None
                        try:
                            inv = db.session.query(Investment).filter(Investment.investor_email.ilike(investor_email.strip())).first()
                            investor_id = inv.id if inv else None
                        except Exception as e:
                            logger.warning(f"Could not find investor_id for {investor_email}: {str(e)}")
                        
                        cls._create_pending_email(
                            batch_id=None,  # No batch for withdrawals
                            investor_id=investor_id,
                            email_type='WITHDRAWAL_RECEIVED',
                            subject=subject,
                            body=body,
                            recipient_email=investor_email,
                            recipient_name=investor_name,
                            amount=amount,
                            fund_name=fund_name
                        )
                        logger.info(f"Created pending withdrawal email for {investor_email}")
                    else:
                        # Send immediately
                        if cls._send_email_immediately(subject, body, investor_email, investor_name):
                            cls._log_email_event(investor_email=investor_email, status='Sent', email_type='WITHDRAWAL_RECEIVED')
                        else:
                            cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_RECEIVED', error_message='Send failed')
                except Exception as e:
                    logger.error(f"Withdrawal received email failed for {investor_email}: {str(e)}")
                    cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_RECEIVED', error_message=str(e))

        threading.Thread(target=process_email, daemon=True).start()

    @classmethod
    def send_withdrawal_approved_email(cls, client_code, investor_name, investor_email, amount, fund_name, trigger_source=None):
        """Notification: Withdrawal request approved (Stage 2 Withdrawal)."""
        app = current_app._get_current_object()
        
        def process_email():
            with app.app_context():
                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)
                logger.info(f"Processing withdrawal approved email for {investor_email} (manual_approval={manual_approval})")
                
                try:
                    if not investor_email:
                        return
                    
                    subject = f"Withdrawal Approved - {fund_name}"
                    body = f"""Dear {investor_name},

We are pleased to inform you that your withdrawal request has been APPROVED.

Client Code: {client_code}
Approved Amount: USD {float(amount):,.2f}
Status: Approved / Scheduled for Distribution

The funds will be processed according to the standard distribution timeline. Thank you for your continued partnership with AIB-AXYS Africa.

Best regards,
AIB-AXYS Africa Investment Team

"""
                    if manual_approval:
                        # Find investor_id if possible
                        investor_id = None
                        try:
                            inv = db.session.query(Investment).filter(Investment.investor_email.ilike(investor_email.strip())).first()
                            investor_id = inv.id if inv else None
                        except Exception as e:
                            logger.warning(f"Could not find investor_id for {investor_email}: {str(e)}")
                        
                        cls._create_pending_email(
                            batch_id=None,  # No batch for withdrawals
                            investor_id=investor_id,
                            email_type='WITHDRAWAL_APPROVED',
                            subject=subject,
                            body=body,
                            recipient_email=investor_email,
                            recipient_name=investor_name,
                            amount=amount,
                            fund_name=fund_name
                        )
                        logger.info(f"Created pending withdrawal approved email for {investor_email}")
                    else:
                        # Send immediately
                        if cls._send_email_immediately(subject, body, investor_email, investor_name):
                            cls._log_email_event(investor_email=investor_email, status='Sent', email_type='WITHDRAWAL_APPROVED')
                        else:
                            cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_APPROVED', error_message='Send failed')
                except Exception as e:
                    logger.error(f"Withdrawal approved email failed for {investor_email}: {str(e)}")
                    cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_APPROVED', error_message=str(e))

        threading.Thread(target=process_email, daemon=True).start()
