from flask import current_app
from flask_mail import Mail, Message
import logging
from datetime import datetime, timezone
import threading

from app.database.database import db
from app.Investments.model import EmailLog, Investment, PendingEmail
from sqlalchemy import insert
from sqlalchemy.orm import scoped_session, sessionmaker

logger = logging.getLogger(__name__)

mail = Mail()

class EmailService:
    """Unified Service for status-driven investor notifications (Stages 1-3)."""

    BCC_EMAIL = "invest@aib-axysafrica.com"
    # Display name only — the underlying mailbox/domain (MAIL_DEFAULT_SENDER,
    # still @aib-axysafrica.com) is unchanged; this is what recipients see as
    # the "From" name.
    SENDER_DISPLAY_NAME = "AXYS INVESTMENT BANK"

    @staticmethod
    def init_app(app):
        mail.init_app(app)

    @classmethod
    def _format_sender(cls, email: str):
        """(display_name, email) — Flask-Mail/email clients render this as
        '"AXYS INVESTMENT BANK" <email>' instead of the bare address."""
        return (cls.SENDER_DISPLAY_NAME, email)

    @classmethod
    def _create_pending_email(cls, batch_id, investor_id, email_type, subject, body, recipient_email, recipient_name=None, amount=None, fund_name=None, batch_name=None, currency_type=None, trigger_source=None):
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
                currency_type=currency_type or 'USD',
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
    def _bulk_create_pending_emails(cls, rows: list) -> int:
        """
        Bulk counterpart to _create_pending_email — one INSERT for every row
        instead of one INSERT+COMMIT per email. At 100k investors, the
        per-row version (used by every stage-change trigger below until this
        was added) meant 100,000 individual round trips just to queue emails
        for approval; this is what "adopt the new style" means here, matching
        the same bulk-insert pattern the bulk-upload commit path already uses.

        Each row is a dict with the same keys _create_pending_email takes as
        kwargs (batch_id, investor_id, email_type, subject, body,
        recipient_email, recipient_name, amount, fund_name, batch_name,
        currency_type, trigger_source) — missing optional keys default the
        same way the model itself defaults them.
        """
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        payload = [
            {
                "batch_id": r.get("batch_id"),
                "investor_id": r.get("investor_id"),
                "email_type": r["email_type"],
                "status": "Pending_Confirmation",
                "subject": r["subject"],
                "body": r["body"],
                "recipient_email": r["recipient_email"],
                "recipient_name": r.get("recipient_name"),
                "amount": r.get("amount"),
                "fund_name": r.get("fund_name"),
                "batch_name": r.get("batch_name"),
                "currency_type": r.get("currency_type") or "USD",
                "created_at": now,
                "trigger_source": r.get("trigger_source"),
            }
            for r in rows
        ]
        try:
            db.session.execute(insert(PendingEmail), payload)
            db.session.commit()
            return len(payload)
        except Exception as e:
            logger.error(f"Failed to bulk-create {len(payload)} pending email(s): {str(e)}")
            db.session.rollback()
            return 0

    @classmethod
    def _bcc_email(cls) -> str:
        return current_app.config.get("MAIL_BCC", cls.BCC_EMAIL)

    @classmethod
    def _render_html_body(cls, text: str, email_type: str = None) -> str:
        """
        Renders the branded card template shared with _send_pending_email_now()
        (the real send path — see app/utils/email_template.py's module docstring
        for why this one is kept in sync despite MANUAL_EMAIL_APPROVAL defaulting
        to True everywhere, which means _send_email_immediately below is dormant).
        """
        from app.utils.email_template import render_branded_email_html, get_email_title
        return render_branded_email_html(get_email_title(email_type), text)

    @classmethod
    def _send_email_immediately(cls, subject, body, recipient_email, recipient_name=None, html=None, attachments=None, email_type=None):
        """Send email immediately without approval."""
        try:
            from app.utils.email_template import attach_brand_logo

            bcc_email = cls._bcc_email()
            if html is None:
                html = cls._render_html_body(body, email_type=email_type)

            msg = Message(
                subject=subject,
                recipients=[recipient_email],
                bcc=[bcc_email],
                body=body,
                html=html,
                sender=cls._format_sender(current_app.config.get('MAIL_DEFAULT_SENDER', bcc_email)),
            )
            attach_brand_logo(msg)

            if attachments:
                for attachment in attachments:
                    msg.attach(
                        attachment['filename'],
                        attachment.get('content_type', 'application/pdf'),
                        attachment['data'],
                    )

            mail.send(msg)
            logger.info(f"Email sent immediately to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
            return False

    @classmethod
    def _build_deposit_statement_attachment(cls, investor, batch_id):
        if not investor or not getattr(investor, 'internal_client_code', None) or not batch_id:
            return None
        try:
            from app.Investments.route import _generate_deposit_receipt_pdf_bytes
            pdf_buffer = _generate_deposit_receipt_pdf_bytes(investor.internal_client_code, int(batch_id))
            if pdf_buffer:
                pdf_buffer.seek(0)
                pdf_bytes = pdf_buffer.getvalue()
                if pdf_bytes:
                    return {
                        'filename': f"deposit-confirmation-{investor.internal_client_code}-{batch_id}.pdf",
                        'content_type': 'application/pdf',
                        'data': pdf_bytes,
                    }
        except Exception as e:
            logger.warning(f"Deposit statement attachment build failed for {investor.internal_client_code}:{batch_id}: {e}")
        return None

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

        # Serialize investments to plain dicts right now, while session is still alive.
        email_items = []
        for inv in investments:
            if isinstance(inv, dict):
                # When passed as dict (from add_investment form), currency_type is already set from user selection
                email_items.append({
                    'investor_id': inv.get('investor_id'),
                    'investor_email': inv.get('investor_email'),
                    'investor_name': inv.get('investor_name') or inv.get('name'),
                    'amount_deposited': inv.get('amount_deposited', 0),
                    'currency_type': inv.get('currency_type') or 'USD',  # Use form selection, fallback to USD only
                })
            else:
                # When passed as ORM object (from Excel upload), extract currency from investment
                email_items.append({
                    'investor_id': getattr(inv, 'id', None),
                    'investor_email': getattr(inv, 'investor_email', None),
                    'investor_name': getattr(inv, 'investor_name', None),
                    'amount_deposited': float(getattr(inv, 'amount_deposited', 0) or 0),
                    'currency_type': getattr(inv, 'currency_type', None) or 'USD',  # Use investment.currency_type, fallback to USD only
                })

        def process_emails():
            with app.app_context():
                from app.Investments.model import Investment
                
                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)

                if manual_approval:
                    # Create pending emails for manual approval
                    created = 0
                    for item in email_items:
                        investor_id = item.get('investor_id')
                        email = item.get('investor_email')
                        name = item.get('investor_name')
                        amount = item.get('amount_deposited')
                        
                        # Fetch actual currency from database, don't rely on what was passed
                        currency = item.get('currency_type') or 'USD'
                        if investor_id and not item.get('currency_type'):
                            try:
                                inv_obj = db.session.query(Investment).filter(Investment.id == investor_id).first()
                                if inv_obj and inv_obj.currency_type:
                                    currency = inv_obj.currency_type
                            except Exception:
                                pass

                        if not email:
                            logger.warning(f"Skipping investor '{name}' — no email address")
                            continue

                        subject = f"Deposit Received - {batch_name}"
                        body = f"""Dear {name},

We have successfully received your investment deposit into batch \"{batch_name}\".

Deposit details
• Capital Amount: {currency} {float(amount):,.2f}
• Status: Deposited (Stage 1/3)

Your funds are now being held securely while we finalize the batch for offshore transfer. You will receive a follow-up email once the transfer has been initiated.

Please find the attached deposit statement for your records.

Best regards,
AXYS INVESTMENT BANK

"""

                        # Fallback: derive investor_id when not explicitly supplied
                        if investor_id is None and not isinstance(investments[0], dict):
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
                            currency_type=currency,
                            trigger_source=trigger_source,
                        )
                        created += 1

                    logger.info(f"Created {created} pending emails for batch '{batch_name}'")
                else:
                    # Send emails immediately
                    sent, failed = 0, 0
                    for item in email_items:
                        try:
                            investor_id = item.get('investor_id')
                            email = item.get('investor_email')
                            name = item.get('investor_name')
                            amount = item.get('amount_deposited')
                            
                            # Fetch actual currency from database, don't rely on what was passed
                            currency = item.get('currency_type') or 'USD'
                            if investor_id and not item.get('currency_type'):
                                try:
                                    inv_obj = db.session.query(Investment).filter(Investment.id == investor_id).first()
                                    if inv_obj:
                                        # First try investment.currency_type
                                        if inv_obj.currency_type:
                                            currency = inv_obj.currency_type
                                        # Then try share_class.currency
                                        elif inv_obj.share_class and inv_obj.share_class.currency:
                                            currency = inv_obj.share_class.currency
                                except Exception as e:
                                    logger.warning(f"Could not fetch investment currency: {e}")

                            subject = f"Deposit Received - {batch_name}"
                            body = f"""Dear {name},

We have successfully received your investment deposit into batch \"{batch_name}\".

Deposit details
• Capital Amount: {currency} {float(amount):,.2f}
• Status: Deposited (Stage 1/3)

Your funds are now being held securely while we finalize the batch for offshore transfer. You will receive a follow-up email once the transfer has been initiated.

Please find the attached deposit statement for your records.

Best regards,
AXYS INVESTMENT BANK
"""
                            html = cls._render_html_body(body, email_type='DEPOSIT_CONFIRMATION')
                            attachment = None
                            inv_obj = None
                            if investor_id:
                                try:
                                    inv_obj = db.session.get(Investment, investor_id)
                                except Exception:
                                    inv_obj = None
                            if inv_obj is None and email:
                                try:
                                    inv_obj = db.session.query(Investment).filter(
                                        Investment.investor_email.ilike(email.strip()),
                                        Investment.batch_id == batch_id,
                                    ).first()
                                except Exception:
                                    inv_obj = None
                            if inv_obj is not None:
                                attachment = cls._build_deposit_statement_attachment(inv_obj, batch_id)
                            attachments = [attachment] if attachment else None
                            if cls._send_email_immediately(subject, body, email, name, html=html, attachments=attachments):
                                sent += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Sent', email_type='DEPOSIT_CONFIRMATION')
                            else:
                                failed += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type='DEPOSIT_CONFIRMATION', error_message='Send failed')
                        except Exception as e:
                            failed += 1
                            logger.error(f"Stage 1 email failed: {str(e)}")
                            cls._log_email_event(
                                investor_email=email if 'email' in locals() else None,
                                investor_id=investor_id if 'investor_id' in locals() else None,
                                batch_id=batch_id,
                                status='Failed',
                                email_type='DEPOSIT_CONFIRMATION',
                                error_message=str(e),
                            )

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
                currency = item.get('currency_type', 'USD')
                body = f"""Dear {name},\n\nWe have successfully received your investment deposit. \n\nBatch: {batch_name}\nCapital Amount: {currency} {float(amount):,.2f}\nStatus: Deposited (Stage 1/3)\n\nYour funds are now being held securely while we finalize the batch for offshore transfer. You will be notified once the transfer is initiated.\n\nBest regards,\nAXYS INVESTMENT BANK\n\n"""

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
                        'currency_type': getattr(inv, 'currency_type', 'USD'),
                        'fund_name': (inv.fund.fund_name if getattr(inv, 'fund', None) else getattr(inv, 'fund_name', None)),
                        'fund_code': (getattr(inv.fund, 'fund_code', None) if getattr(inv, 'fund', None) else None),
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
                    # Build every pending-email row in memory, then one bulk
                    # INSERT at the end (see _bulk_create_pending_emails) instead
                    # of one INSERT+COMMIT per investor — was 100,000 individual
                    # round trips for a 100k-investor batch.
                    pending_rows = []
                    skipped_no_email = 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        currency = item.get('currency_type', 'USD')

                        if not email:
                            skipped_no_email += 1
                            continue
                        principal = float(item.get('amount_deposited', 0) or 0)
                        transaction_fee = float(item.get('transfer_fee_deducted', 0) or 0)
                        entry_fee = float(item.get('deployment_fee_deducted', 0) or 0)
                        net = float(item.get('net_principal', 0) or 0)
                        weight_pct = ((principal / batch_total_principal) * 100) if batch_total_principal > 0 else 0.0
                        from app.utils.statement_theme import is_dangote_dprp_fund
                        transfer_label = "Shares" if is_dangote_dprp_fund([item.get('fund_name')], [item.get('fund_code')]) else "Fund"

                        subject = f"Funds Successfully Transferred to {transfer_label} - {batch_name}"
                        body = f"""Dear {name},

We are pleased to inform you that your funds in batch "{batch_name}" have been successfully transferred to our offshore investment partner.

Status: Transferred (Stage 2/3)

The funds are now awaiting final deployment into the active portfolio. We will notify you once the deployment is confirmed and your returns begin to accrue.

Initial Deposit: {currency} {principal:,.2f}
Allocated Transaction Fee: -{currency} {transaction_fee:,.2f}
Allocated Entry Fee: -{currency} {entry_fee:,.2f}
New Active Balance: {currency} {net:,.2f}

Best regards,
AXYS INVESTMENT BANK

"""
                        pending_rows.append({
                            "batch_id": batch_id,
                            "investor_id": investor_id,
                            "email_type": "OFFSHORE_TRANSFER",
                            "subject": subject,
                            "body": body,
                            "recipient_email": email,
                            "recipient_name": name,
                            "batch_name": batch_name,
                            "currency_type": currency,
                            "trigger_source": trigger_source,
                        })
                    if skipped_no_email:
                        logger.warning(f"Skipped {skipped_no_email} investor(s) with no email address")
                    created = cls._bulk_create_pending_emails(pending_rows)
                    logger.info(f"Created {created} pending emails for batch '{batch_name}'")
                else:
                    # Send emails immediately
                    sent, failed = 0, 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        currency = item.get('currency_type', 'USD')
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
                            from app.utils.statement_theme import is_dangote_dprp_fund
                            transfer_label = "Shares" if is_dangote_dprp_fund([item.get('fund_name')], [item.get('fund_code')]) else "Fund"
                            subject = f"Funds Successfully Transferred to {transfer_label} - {batch_name}"
                            body = f"""Dear {name},

We are pleased to inform you that your funds in batch "{batch_name}" have been successfully transferred to our offshore investment partner.

Status: Transferred (Stage 2/3)

The funds are now awaiting final deployment into the active portfolio. We will notify you once the deployment is confirmed and your returns begin to accrue.

Initial Deposit: {currency} {principal:,.2f}
Batch Total Deployed: {currency} {batch_total_net:,.2f}
Allocated Transaction Fee: -{currency} {transaction_fee:,.2f}
Allocated Entry Fee: -{currency} {entry_fee:,.2f}
New Active Balance: {currency} {net:,.2f}

Best regards,
AXYS INVESTMENT BANK

"""
                            if cls._send_email_immediately(subject, body, email, name, email_type='OFFSHORE_TRANSFER'):
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
    def send_investment_active_batch(cls, batch, trigger_source=None, oversubscribed_investor_ids=None):
        """
        Stage 3: Investment Active (Deployed).
        Triggered when 'Confirm Deployment' is checked or Date Deployed is saved.
        Includes transaction cost breakdown in the email.

        Every investor in the batch gets the same standard deployment-confirmation
        email — oversubscription/refund details are NOT included here (that used to
        be a variant of this same email, but oversubscription is a one-time event
        tied to a single deployment, not something that belongs mixed into a
        recurring investor communication). See send_oversubscription_refund_notices
        below for the separate, one-time notice sent to oversubscribed investors.
        oversubscribed_investor_ids is still accepted (callers pass it unchanged)
        but is no longer used here — kept so call sites don't need updating twice.
        """
        app = current_app._get_current_object()

        # Extract all data from ORM objects BEFORE the thread starts
        batch_name = getattr(batch, 'batch_name', 'Unknown Batch')
        batch_id = getattr(batch, 'id', None)
        deployment_nav = float(getattr(batch, "deployment_nav", 0) or 0)
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
                'transfer_fee_deducted': float(getattr(inv, 'transfer_fee_deducted', 0) or 0),
                'deployment_fee_deducted': float(getattr(inv, 'deployment_fee_deducted', 0) or 0),
                'shares_owned': float(getattr(inv, 'shares_owned', 0) or 0) if getattr(inv, 'shares_owned', None) is not None else None,
                'nav_per_share': float(getattr(inv, 'previous_nav_price', None) or deployment_nav) if (getattr(inv, 'previous_nav_price', None) is not None or deployment_nav) else None,
                'currency_type': getattr(inv, 'currency_type', 'USD'),
            }
            for inv in getattr(batch, 'investments', [])
        ]

        unique_recipients = {
            item.get('investor_id') or item.get('investor_email')
            for item in email_items
            if item.get('investor_email')
        }

        def build_email_content(item):
            """Returns (email_type, subject, body) — the same standard deployment
            confirmation for every investor in the batch, oversubscribed or not.
            Oversubscription/refund info is never mixed into this email — see
            send_oversubscription_refund_notices for that separate, one-time notice."""
            name = item.get('investor_name', 'Investor')
            original_amount = item.get('amount_deposited', 0)
            transfer_fee = item.get('transfer_fee_deducted', 0)
            entry_fee = item.get('deployment_fee_deducted', 0)
            total_fees = transfer_fee + entry_fee
            net_amount = original_amount - total_fees  # pre-oversubscription net principal
            shares_owned = item.get("shares_owned")
            nav_per_share = item.get("nav_per_share")
            currency = item.get('currency_type', 'USD')

            nav_lines = ""
            if shares_owned is not None and nav_per_share is not None and nav_per_share > 0:
                nav_lines = f"""
Shares: {shares_owned:,.4f}
NAV / Share: {nav_per_share:,.6f}"""

            subject = f"Funds Successfully Deployed: {batch_name}"
            fee_lines = f"""
Transaction Fee Contribution: -{currency} {transfer_fee:,.2f}
Entry Fee Contribution: -{currency} {entry_fee:,.2f}
Total Fees: -{currency} {total_fees:,.2f}
Net Deployed Amount: {currency} {net_amount:,.2f}"""
            body = f"""Dear {name},

Your investment in {batch_name} has been successfully deployed and is now ACTIVE.

DEPLOYMENT SUMMARY

Original Deposit Amount: {currency} {original_amount:,.2f}{fee_lines}{nav_lines}

Deployment Date: {deploy_date}
Status: Active (Stage 3/3)

Thank you for investing with AXYS INVESTMENT BANK.

Best regards,
AXYS INVESTMENT BANK
"""
            return 'INVESTMENT_ACTIVE', subject, body

        def process_emails():
            with app.app_context():
                manual_approval = app.config.get('MANUAL_EMAIL_APPROVAL', False)
                logger.info(f"Processing Stage 3 emails for batch '{batch_name}' (manual_approval={manual_approval})")

                if manual_approval:
                    # Build every pending-email row in memory, then one bulk
                    # INSERT at the end (see _bulk_create_pending_emails) instead
                    # of one INSERT+COMMIT per investor — same fix as Stage 2.
                    pending_rows = []
                    skipped_no_email = 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')
                        currency = item.get('currency_type', 'USD')

                        if not email:
                            skipped_no_email += 1
                            continue

                        email_type, subject, body = build_email_content(item)
                        pending_rows.append({
                            "batch_id": batch_id,
                            "investor_id": investor_id,
                            "email_type": email_type,
                            "subject": subject,
                            "body": body,
                            "recipient_email": email,
                            "recipient_name": name,
                            "batch_name": batch_name,
                            "currency_type": currency,
                            "trigger_source": trigger_source,
                        })
                    if skipped_no_email:
                        logger.warning(f"Skipped {skipped_no_email} investor(s) with no email address")
                    created = cls._bulk_create_pending_emails(pending_rows)
                    logger.info(f"Created {created} pending emails for batch '{batch_name}'")
                else:
                    # Send emails immediately
                    sent, failed = 0, 0
                    for item in email_items:
                        email = item.get('investor_email')
                        name = item.get('investor_name', 'Investor')
                        investor_id = item.get('investor_id')

                        if not email:
                            cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', error_message='Missing email')
                            failed += 1
                            continue
                        try:
                            email_type, subject, body = build_email_content(item)
                            if cls._send_email_immediately(subject, body, email, name, email_type=email_type):
                                sent += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Sent', email_type=email_type)
                                logger.info(f"Stage 3 email sent to {email}")
                            else:
                                failed += 1
                                cls._log_email_event(investor_email=email, investor_id=investor_id, batch_id=batch_id, status='Failed', email_type=email_type, error_message='Send failed')
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
    def send_oversubscription_refund_notices(cls, batch, oversubscribed_investor_ids, trigger_source=None):
        """
        One-time Oversubscription/Refund Notice — triggered automatically once,
        at the same moment a batch is deployed WITH oversubscription applied
        (called right alongside send_investment_active_batch, never separately).
        Distinct from the regular deployment-confirmation email: this is about
        what happened to the undeployed slice of the deposit specifically, and
        it lives alongside the withdrawal it's tied to (Withdrawals page), not
        mixed into the investor's recurring statement/email history.

        Unlike the other trigger methods here, this ALWAYS queues for manual
        approval — never auto-sends immediately — regardless of the
        MANUAL_EMAIL_APPROVAL setting, per explicit product requirement (a
        refund notice going out unreviewed is a worse failure mode than a
        deployment-confirmation email doing the same).

        Idempotency: each PendingEmail row is linked (via investor_id + the
        OVERSUBSCRIPTION_REFUND_NOTICE email_type) back to a specific investor's
        refund. The actual "don't resend" guarantee is
        Withdrawal.oversubscription_notice_sent_at, set once _send_pending_email_now
        successfully sends this email_type — that flag, not this trigger, is what a
        caller should check before calling this again for the same deployment.
        """
        app = current_app._get_current_object()
        oversubscribed_ids = set(oversubscribed_investor_ids or [])
        if not oversubscribed_ids:
            return

        batch_name = getattr(batch, 'batch_name', 'Unknown Batch')
        batch_id = getattr(batch, 'id', None)

        investment_ids = [
            getattr(inv, 'id', None) for inv in getattr(batch, 'investments', [])
            if getattr(inv, 'id', None) in oversubscribed_ids
        ]

        def process_notices():
            with app.app_context():
                from app.Investments.route import _get_oversubscription_refund_context
                from app.Investments.model import Investment

                investments = db.session.query(Investment).filter(Investment.id.in_(investment_ids)).all()
                logger.info(f"Processing {len(investments)} oversubscription refund notice(s) for batch '{batch_name}'")

                pending_rows = []
                skipped = 0
                for inv in investments:
                    email = getattr(inv, 'investor_email', None)
                    name = getattr(inv, 'investor_name', 'Investor')
                    if not email or not inv.internal_client_code or inv.fund_id is None:
                        skipped += 1
                        continue

                    ctx = _get_oversubscription_refund_context(inv.internal_client_code, inv.fund_id)
                    if ctx is None:
                        skipped += 1
                        continue

                    subject = f"Oversubscription / Refund Notice: {batch_name}"
                    body = f"""Dear {name},

{batch_name} was oversubscribed — total investor commitments exceeded what could actually be deployed into shares. As a result, part of your deposit was not deployed and is being refunded.

Amount Deployed Into Shares: {ctx['currency']} {float(ctx['total_deployed']):,.2f}
Refund Amount: {ctx['currency']} {float(ctx['total_refund']):,.2f}
Refund Status: {ctx['refund_status']}

Your refund is processed through our standard withdrawal approval flow. You will receive a separate notification once it is approved and scheduled for payout. This is a one-time notice for this deployment — it will not be repeated on future statements.

Best regards,
AXYS INVESTMENT BANK
"""
                    pending_rows.append({
                        "batch_id": batch_id,
                        "investor_id": inv.id,
                        "email_type": "OVERSUBSCRIPTION_REFUND_NOTICE",
                        "subject": subject,
                        "body": body,
                        "recipient_email": email,
                        "recipient_name": name,
                        "batch_name": batch_name,
                        "currency_type": ctx["currency"],
                        "trigger_source": trigger_source,
                    })

                if skipped:
                    logger.warning(f"Skipped {skipped} oversubscription notice(s) — missing email/client_code/fund or no refund context")
                created = cls._bulk_create_pending_emails(pending_rows)
                logger.info(f"Created {created} oversubscription refund notice(s) for batch '{batch_name}' (queued for manual approval)")

        threading.Thread(target=process_notices, daemon=True).start()

    @classmethod
    def send_withdrawal_received_email(cls, client_code, investor_name, investor_email, amount, fund_name, currency='USD', trigger_source=None):
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
Withdrawal Amount: {currency} {float(amount):,.2f}
Status: Received / Processing

Our team is currently reviewing your request. You will receive a follow-up notification once the withdrawal is approved and scheduled for distribution.

Best regards,
AXYS INVESTMENT BANK

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
                            fund_name=fund_name,
                            currency_type=currency,
                        )
                        logger.info(f"Created pending withdrawal email for {investor_email}")
                    else:
                        # Send immediately
                        if cls._send_email_immediately(subject, body, investor_email, investor_name, email_type='WITHDRAWAL_RECEIVED'):
                            cls._log_email_event(investor_email=investor_email, status='Sent', email_type='WITHDRAWAL_RECEIVED')
                        else:
                            cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_RECEIVED', error_message='Send failed')
                except Exception as e:
                    logger.error(f"Withdrawal received email failed for {investor_email}: {str(e)}")
                    cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_RECEIVED', error_message=str(e))

        threading.Thread(target=process_email, daemon=True).start()

    @classmethod
    def send_withdrawal_approved_email(cls, client_code, investor_name, investor_email, amount, fund_name, currency='USD', trigger_source=None):
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
Approved Amount: {currency} {float(amount):,.2f}
Status: Approved / Scheduled for Distribution

The funds will be processed according to the standard distribution timeline. Thank you for your continued partnership with AXYS INVESTMENT BANK.

Best regards,
AXYS INVESTMENT BANK

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
                            fund_name=fund_name,
                            currency_type=currency,
                        )
                        logger.info(f"Created pending withdrawal approved email for {investor_email}")
                    else:
                        # Send immediately
                        if cls._send_email_immediately(subject, body, investor_email, investor_name, email_type='WITHDRAWAL_APPROVED'):
                            cls._log_email_event(investor_email=investor_email, status='Sent', email_type='WITHDRAWAL_APPROVED')
                        else:
                            cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_APPROVED', error_message='Send failed')
                except Exception as e:
                    logger.error(f"Withdrawal approved email failed for {investor_email}: {str(e)}")
                    cls._log_email_event(investor_email=investor_email, status='Failed', email_type='WITHDRAWAL_APPROVED', error_message=str(e))

        threading.Thread(target=process_email, daemon=True).start()
