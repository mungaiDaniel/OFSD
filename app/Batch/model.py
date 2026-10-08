from app.database.database import db
from base_model import Base
from app.database.product_type import ProductTypeEnum, FUNDS
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Date, Index, UniqueConstraint, Text, event, text


class Batch(Base, db.Model):
    __tablename__ = 'batches'
    __table_args__ = (
        UniqueConstraint('batch_name', name='uq_batches_batch_name'),
        Index('ix_batches_share_class_is_open', 'share_class_id', 'is_open'),
        Index('ix_batches_product_type', 'product_type'),
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
    
    # FUNDS vs SHARES (see app.database.product_type). Derived from the batch's
    # fund identity at creation time and immutable after — every deposit/holding
    # in this batch must match it (see Investment.product_type).
    product_type = Column(ProductTypeEnum, nullable=False, default=FUNDS, server_default=FUNDS)

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

    # Oversubscription banner (see app.logic.shares_deployment_service): True when a
    # SHARES batch's shares_allocated_total < shares_demand_total. Previously also set by
    # the old flat-rate DPRP allocation (Task 2/3 replaced that with the NGN-based
    # allocation below); allocation_rate is unused by the new logic and kept only so
    # historical batches deployed under the old system still display their rate.
    is_oversubscribed = Column(Boolean, default=False, nullable=False)
    allocation_rate = Column(Numeric(7, 4), nullable=True)  # DEPRECATED — see shares_deployment_service

    # SHARES-only deployment inputs/results (see app.logic.shares_deployment_service) —
    # entered manually at the Deployed step, locked once batch.deployment_confirmed is
    # True. total_shares (above) doubles as "sum of shares actually allocated" for a
    # SHARES batch, matching its existing meaning ("Sum of all investor shares in batch").
    shares_exchange_rate_ngn = Column(Numeric(20, 6), nullable=True)  # NGN per 1 USD, as entered by staff
    shares_price_per_share_ngn = Column(Numeric(20, 4), nullable=True)
    shares_allocated_total = Column(Integer, nullable=True)  # Whole shares allotted by the issuer
    shares_demand_total = Column(Integer, nullable=True)  # SUM(max_shares_i) before any allocation/rounds
    shares_unallocated_total = Column(Integer, nullable=True)  # shares_allocated_total minus what was actually allocated

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


@event.listens_for(Batch, "before_insert")
def _inherit_product_type_from_share_class(mapper, connection, target):
    """
    Task 8: a batch always takes its product_type from its share class (which
    in turn takes it from its CoreFund — see ShareClass's own event) — the
    same "fund/share/batch/holding product always matches" chain
    Investment.product_type already enforces against this very column. Only
    runs at creation: share_class_id is never reassigned after a batch
    exists.
    """
    if target.share_class_id is None:
        return
    row = connection.execute(
        text("SELECT product_type FROM share_classes WHERE id = :share_class_id"),
        {"share_class_id": target.share_class_id},
    ).first()
    if row is None:
        return
    share_class_product_type = row[0]
    if target.product_type and target.product_type != share_class_product_type:
        raise ValueError(
            f"Cannot create a {target.product_type} batch for share class {target.share_class_id}, "
            f"which is a {share_class_product_type} share class."
        )
    target.product_type = share_class_product_type

    def __repr__(self):
        return f'<Batch {self.batch_name} - {self.certificate_number}>'