from app.database.database import db
from base_model import Base
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Date, Index, UniqueConstraint, Text


class Batch(Base, db.Model):
    __tablename__ = 'batches'
    __table_args__ = (
        UniqueConstraint('batch_name', name='uq_batches_batch_name'),
        Index('ix_batches_share_class_is_open', 'share_class_id', 'is_open'),
    )
    
    id = Column(Integer, primary_key=True)
    batch_name = Column(String(100), nullable=False)
    certificate_number = Column(String(100), unique=True, nullable=True)
    total_principal = Column(Numeric(20, 2), default=0.00)
    date_deployed = Column(DateTime, nullable=True)
    duration_days = Column(Integer, default=30)
    date_closed = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False)  # Changed from True to False for new batches
    is_transferred = Column(Boolean, default=False)
    deployment_confirmed = Column(Boolean, default=False)  # Tracks Stage 3 confirmation
    stage = Column(Integer, default=1)  # Current stage: 1=Deposited, 2=Transferred, 3=Deployed, 4=Active
    transaction_cost = Column(Numeric(20, 2), default=0.00, nullable=False)  # Total deployment fee in USD
    transfer_transaction_cost = Column(Numeric(20, 2), default=0.00, nullable=False)  # Total transfer fee in USD

    # Cached total current standing (sum of BatchController._calculate_batch_investment_values
    # across every investment in this batch), refreshed at write time (deploy, withdrawal
    # approval, valuation commit — see BatchController.refresh_cached_total_capital) instead of
    # being recomputed on every page load. NULL means never computed yet (old batches before
    # this existed, or a batch with zero investments) — read paths fall back to a live
    # calculation and self-heal by storing it when this is NULL.
    cached_total_capital = Column(Numeric(20, 2), nullable=True)
    cached_total_capital_at = Column(DateTime(timezone=True), nullable=True)
    
    # Share-based valuation columns
    share_class_id = Column(Integer, ForeignKey('share_classes.id', ondelete='SET NULL'), nullable=True)
    is_open = Column(Boolean, default=True, nullable=False)  # True while accepting investors, False after Thursday close
    auto_close_at = Column(DateTime(timezone=True), nullable=True)  # Next Thursday 9:00 AM EAT
    exported_at = Column(DateTime(timezone=True), nullable=True)  # When batch Excel was exported
    total_shares = Column(Numeric(20, 6), nullable=True)  # Sum of all investor shares in batch
    deployment_nav = Column(Numeric(20, 6), nullable=True)  # NAV per share at deployment
    deployment_total_nav = Column(Numeric(20, 2), nullable=True)  # Deployment NAV per share * total_shares
    deployment_breakdown = Column(Text, nullable=True)  # JSON serialization of multi-class deployment totals
    deployment_date_actual = Column(Date, nullable=True)  # Actual deployment date from Head Office confirmation

    # DPRP oversubscription pro-rata allocation (see is_dangote_dprp_fund) — set once, at
    # deployment time, when the admin toggles "Oversubscribed" in the deploy modal because the
    # batch's total deposits exceed what could actually be deployed into DPRP shares.
    is_oversubscribed = Column(Boolean, default=False, nullable=False)
    allocation_rate = Column(Numeric(7, 4), nullable=True)  # e.g. 60.0000 = 60% deployed, 40% refunded

    # Relationships
    share_class = db.relationship('ShareClass', foreign_keys=[share_class_id], uselist=False, backref=db.backref('batches', lazy='dynamic'))
    performance = db.relationship('Performance', foreign_keys='Performance.batch_id', uselist=False, back_populates='batch', overlaps="performance_records")
    investments = db.relationship('Investment', foreign_keys='Investment.batch_id', back_populates='batch')

    @property
    def expected_close_date(self):
        """Calculate expected close date based on deployment date + duration. Returns None if date_deployed is None."""
        if self.date_deployed is None:
            return None
        deployed = self.date_deployed
        # Ensure timezone-aware for comparison with other timezone-aware datetimes
        if deployed.tzinfo is None:
            deployed = deployed.replace(tzinfo=timezone.utc)
        return deployed + timedelta(days=self.duration_days)

    def __repr__(self):
        return f'<Batch {self.batch_name} - {self.certificate_number}>'