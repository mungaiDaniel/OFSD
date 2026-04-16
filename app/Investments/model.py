from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, ForeignKey, UniqueConstraint, Index
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class Investment(Base, db.Model):
    __tablename__ = 'investments'

    id = Column(Integer, primary_key=True)
    investor_name = Column(String(100), nullable=False)
    investor_email = Column(String(100), nullable=False)
    investor_phone = Column(String(20))
    internal_client_code = Column(String(50), nullable=False)  # Unique ID from Excel (now allows duplicates across batches)
    amount_deposited = Column(Numeric(20, 2), nullable=False)
    deployment_fee_deducted = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Pro-rata transaction cost deducted at deployment
    transfer_fee_deducted = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Pro-rata transfer cost deducted at transfer
    date_deposited = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    date_transferred = Column(DateTime, nullable=True)  # When actually transferred/deployed
    # DEPRECATED: keep for backward compatibility while migrating.
    # Source of truth is fund_id -> core_funds.
    fund_name = Column(String(100), nullable=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    fund_id = Column(Integer, ForeignKey('core_funds.id'), nullable=True)

    # New fields for enhanced investor tracking
    wealth_manager = Column(String(100), nullable=True)
    IFA = Column(String(100), nullable=True)  # Independent Financial Advisor
    contract_note = Column(String(255), nullable=True)  # URL or reference to contract
    valuation = Column(Numeric(20, 2), nullable=True)  # Current valuation amount

    # Removed Composite unique constraint: internal_client_code + batch_id must be unique

    # Relationships
    batch = db.relationship('Batch', back_populates='investments')
    fund = db.relationship('CoreFund', backref='investments')

    @property
    def net_principal(self):
        """Calculate the current net principal after all deductions."""
        return self.amount_deposited - self.transfer_fee_deducted - self.deployment_fee_deducted

    def __repr__(self):
        return f'<Investment {self.investor_name} ({self.internal_client_code}) - Fund: {self.fund_name} - {self.amount_deposited}>'


class EmailLog(Base, db.Model):
    __tablename__ = 'email_logs'

    id = Column(Integer, primary_key=True)
    investor_id = Column(Integer, ForeignKey('investments.id'), nullable=True, index=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=True, index=True)
    status = Column(String(20), nullable=False)  # Sent/Failed/Summary
    email_type = Column(String(50), nullable=True, index=True)  # DEPOSIT_CONFIRMATION/OFFSHORE_TRANSFER/INVESTMENT_ACTIVE
    recipient_count = Column(Integer, nullable=True, default=0)
    success_count = Column(Integer, nullable=True, default=0)
    failure_count = Column(Integer, nullable=True, default=0)
    error_message = Column(String(512), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    retry_count = Column(Integer, nullable=False, default=0)
    trigger_source = Column(String(120), nullable=True, index=True)

    investor = db.relationship('Investment', backref='email_logs')
    batch = db.relationship('Batch', backref='email_logs')

    def __repr__(self):
        return f"<EmailLog {self.status} investor={self.investor_id} batch={self.batch_id} at {self.timestamp}>"  


class PendingEmail(Base, db.Model):
    __tablename__ = 'pending_emails'

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=True, index=True)
    investor_id = Column(Integer, ForeignKey('investments.id'), nullable=True, index=True)
    email_type = Column(String(50), nullable=False, index=True)  # DEPOSIT_CONFIRMATION/OFFSHORE_TRANSFER/INVESTMENT_ACTIVE/WITHDRAWAL_RECEIVED/etc.
    status = Column(String(20), nullable=False, default='Pending_Confirmation')  # Pending_Confirmation/Confirmed/Cancelled
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    recipient_email = Column(String(100), nullable=False)
    recipient_name = Column(String(100), nullable=True)
    amount = Column(Numeric(20, 2), nullable=True)  # For deposit/withdrawal amounts
    fund_name = Column(String(100), nullable=True)
    batch_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True), nullable=True)
    trigger_source = Column(String(120), nullable=True, index=True)

    # Relationships
    batch = db.relationship('Batch', backref='pending_emails')
    investor = db.relationship('Investment', backref='pending_emails')

    def __repr__(self):
        return f"<PendingEmail {self.email_type} to {self.recipient_email} status={self.status}>"  


WITHDRAWAL_STATUS_PENDING = "Pending"
WITHDRAWAL_STATUS_APPROVED = "Approved"
WITHDRAWAL_STATUS_REJECTED = "Rejected"
WITHDRAWAL_STATUS_PROCESSED = "Processed"
WITHDRAWAL_STATUS_COMPLETED = "Completed"
# Executed: withdrawal has been permanently embedded in a committed EpochLedger row.
# It will NOT be subtracted again by future valuation runs.
WITHDRAWAL_STATUS_EXECUTED = "Executed"

WITHDRAWAL_STATUSES = (
    WITHDRAWAL_STATUS_PENDING,
    WITHDRAWAL_STATUS_APPROVED,
    WITHDRAWAL_STATUS_REJECTED,
    WITHDRAWAL_STATUS_PROCESSED,
    WITHDRAWAL_STATUS_COMPLETED,
    WITHDRAWAL_STATUS_EXECUTED,
)

# FINAL_WITHDRAWAL_STATUSES is used by balance / display queries to sum all outflows
# that have left the investor's account (regardless of whether they've already been
# captured in an epoch ledger).  Executed MUST be included so historical displays
# are not broken after a valuation confirm.
FINAL_WITHDRAWAL_STATUSES = (
    WITHDRAWAL_STATUS_APPROVED,
    WITHDRAWAL_STATUS_PROCESSED,
    WITHDRAWAL_STATUS_COMPLETED,
    WITHDRAWAL_STATUS_EXECUTED,
)


def normalize_withdrawal_status(status):
    if not status:
        return WITHDRAWAL_STATUS_PENDING
    normalized = str(status).strip().capitalize()
    return normalized if normalized in WITHDRAWAL_STATUSES else WITHDRAWAL_STATUS_PENDING


class Withdrawal(Base, db.Model):
    """
    Tracks outflows per investor (internal_client_code) and fund.
    Used by the EpochLedger reconciliation logic.
    """
    __tablename__ = 'withdrawals'

    id = Column(Integer, primary_key=True)
    internal_client_code = Column(String(50), nullable=False, index=True)
    fund_id = Column(Integer, ForeignKey('core_funds.id'), nullable=True, index=True)
    # DEPRECATED: for display/backfill only
    fund_name = Column(String(100), nullable=True, index=True)
    amount = Column(Numeric(20, 2), nullable=False)
    date_withdrawn = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    status = Column(String(20), nullable=False, default='Pending')  # Pending|Approved|Rejected
    approved_at = Column(DateTime, nullable=True)
    note = Column(String(255), nullable=True)

    # Optional linkage to a batch (if the withdrawal was initiated in a batch context)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=True)

    __table_args__ = (
        Index('ix_withdrawals_code_fund_date', 'internal_client_code', 'fund_id', 'date_withdrawn'),
    )

    # Relationships
    fund = db.relationship('CoreFund', backref='withdrawals')
    batch = db.relationship('Batch', backref='withdrawals')

    def __repr__(self):
        return f"<Withdrawal {self.internal_client_code} {self.fund_name} {self.amount} on {self.date_withdrawn}>"


class EpochLedger(Base, db.Model):
    """
    Immutable epoch-by-epoch ledger for compounding balances.

    Keyed by (internal_client_code, fund_name, epoch_start, epoch_end).
    Hash chain is maintained per (internal_client_code, fund_name).
    """
    __tablename__ = 'epoch_ledger'

    id = Column(Integer, primary_key=True)

    internal_client_code = Column(String(50), nullable=False, index=True)
    fund_name = Column(String(100), nullable=False, index=True)

    epoch_start = Column(DateTime, nullable=False, index=True)
    epoch_end = Column(DateTime, nullable=False, index=True)

    # Period performance rate as a decimal fraction (e.g. 0.05 for 5%)
    performance_rate = Column(Numeric(12, 8), nullable=False)

    start_balance = Column(Numeric(20, 2), nullable=False)
    deposits = Column(Numeric(20, 2), nullable=False, default=0.00)
    withdrawals = Column(Numeric(20, 2), nullable=False, default=0.00)
    profit = Column(Numeric(20, 2), nullable=False, default=0.00)
    end_balance = Column(Numeric(20, 2), nullable=False)

    previous_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False, unique=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        UniqueConstraint(
            'internal_client_code', 'fund_name', 'epoch_start', 'epoch_end',
            name='_epoch_ledger_investor_fund_period_uc'
        ),
        Index('ix_epoch_ledger_code_fund_end', 'internal_client_code', 'fund_name', 'epoch_end'),
    )

    # Link to investments via internal_client_code (no FK because investments are per-batch)
    investments = db.relationship(
        'Investment',
        primaryjoin="foreign(Investment.internal_client_code)==EpochLedger.internal_client_code",
        viewonly=True,
    )

    def __repr__(self):
        return (
            f"<EpochLedger {self.internal_client_code} {self.fund_name} "
            f"{self.epoch_start.date()}→{self.epoch_end.date()} end={self.end_balance}>"
        )
