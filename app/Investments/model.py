from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, UniqueConstraint, Index
from app.database.database import db
from base_model import Base
from datetime import datetime


class Investment(Base, db.Model):
    __tablename__ = 'investments'

    id = Column(Integer, primary_key=True)
    investor_name = Column(String(100), nullable=False)
    investor_email = Column(String(100), nullable=False)
    investor_phone = Column(String(20))
    internal_client_code = Column(String(50), nullable=False)  # Unique ID from Excel (now allows duplicates across batches)
    amount_deposited = Column(Numeric(20, 2), nullable=False)
    date_deposited = Column(DateTime, nullable=False, default=datetime.utcnow)
    date_transferred = Column(DateTime, nullable=True)  # When actually transferred/deployed
    # DEPRECATED: keep for backward compatibility while migrating.
    # Source of truth is fund_id -> core_funds.
    fund_name = Column(String(100), nullable=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    fund_id = Column(Integer, ForeignKey('core_funds.id'), nullable=True)

    # Composite unique constraint: internal_client_code + batch_id must be unique
    __table_args__ = (
        UniqueConstraint('internal_client_code', 'batch_id', name='_customer_batch_uc'),
    )

    # Relationships
    batch = db.relationship('Batch', back_populates='investments')
    fund = db.relationship('CoreFund', backref='investments')

    def __repr__(self):
        return f'<Investment {self.investor_name} ({self.internal_client_code}) - Fund: {self.fund_name} - {self.amount_deposited}>'


class Withdrawal(Base, db.Model):
    """
    Tracks outflows per investor (internal_client_code) and fund.
    Used by the EpochLedger reconciliation logic.
    """
    __tablename__ = 'withdrawals'

    id = Column(Integer, primary_key=True)
    internal_client_code = Column(String(50), nullable=False, index=True)
    fund_id = Column(Integer, ForeignKey('core_funds.id'), nullable=False, index=True)
    # DEPRECATED: for display/backfill only
    fund_name = Column(String(100), nullable=True, index=True)
    amount = Column(Numeric(20, 2), nullable=False)
    date_withdrawn = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
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

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

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
