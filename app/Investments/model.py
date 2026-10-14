from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Numeric, ForeignKey, UniqueConstraint, Index, Enum, event, text
from app.database.database import db
from app.database.product_type import ProductTypeEnum, FUNDS
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class Investment(Base, db.Model):
    __tablename__ = 'investments'

    id = Column(Integer, primary_key=True)
    investor_name = Column(String(100), nullable=False)
    investor_email = Column(String(100), nullable=False)
    investor_phone = Column(String(20))
    internal_client_code = Column(String(50), nullable=False, index=True)  # Unique ID from Excel (now allows duplicates across batches)
    amount_deposited = Column(Numeric(20, 2), nullable=False)
    deployment_fee_deducted = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Pro-rata transaction cost deducted at deployment
    transfer_fee_deducted = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Pro-rata transfer cost deducted at transfer
    date_deposited = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    date_transferred = Column(DateTime, nullable=True)  # When actually transferred/deployed
    deposit_date = Column(Date, nullable=True)  # Actual date client deposited money (distinct from system timestamp)
    # DEPRECATED: keep for backward compatibility while migrating.
    # Source of truth is fund_id -> core_funds.
    fund_name = Column(String(100), nullable=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False, index=True)
    fund_id = Column(Integer, ForeignKey('core_funds.id'), nullable=True, index=True)
    share_class_id = Column(Integer, ForeignKey('share_classes.id', ondelete='SET NULL'), nullable=True)

    # Inherited from this deposit's batch (see Batch.product_type) — kept on the
    # row itself (rather than always joining to batches) so list/filter queries
    # over deposits/holdings by product can use a plain indexed column. Set
    # automatically by the _inherit_product_type_from_batch event below when not
    # already provided by the caller.
    product_type = Column(ProductTypeEnum, nullable=False, default=FUNDS, server_default=FUNDS, index=True)

    # New fields for enhanced investor tracking
    wealth_manager = Column(String(100), nullable=True)
    IFA = Column(String(100), nullable=True)  # Independent Financial Advisor
    contract_note = Column(String(255), nullable=True)  # URL or reference to contract
    valuation = Column(Numeric(20, 2), nullable=True)  # Current valuation amount
    original_deposit_amount = Column(Numeric(20, 2), nullable=True)
    current_market_value = Column(Numeric(20, 2), nullable=True)
    shares_owned = Column(Numeric(24, 4), nullable=True)
    share_series = Column(String(100), nullable=True)
    currency_type = Column(Enum("USD", "KES", "NGN", name="currency_type_enum"), nullable=True)
    opening_market_value = Column(Numeric(20, 2), nullable=True)  # shares_owned × nav_per_share at deployment
    previous_nav_price = Column(Numeric(20, 6), nullable=True)  # Previous NAV for display on investor detail
    rounding_adjustment = Column(Numeric(20, 4), nullable=True, default=Decimal("0.0000"))  # Adjustment for official value reconciliation
    official_receipt_value = Column(Numeric(20, 2), nullable=True)  # Official Head Office receipt value

    # SHARES-only (see app.logic.shares_transfer_service): balance after the entry fee
    # is deducted from the raw deposit, before the proportional transaction cost is
    # taken out of it. NULL for FUNDS investments — they never populate this field.
    balance_after_entry_fee_usd = Column(Numeric(20, 2), nullable=True)

    # SHARES-only (see app.logic.shares_deployment_service), set once at the Deployed
    # step: the exact rate/price used for THIS investment, stored per-row (not just
    # read off the batch) so the historical record survives even if the batch's own
    # fields are ever cleared by an admin reversal. net_ngn = net_principal * exchange
    # rate; shares_owned (below) holds the whole shares actually allocated, and
    # oversubscription_refund_amount (below) doubles as this investment's refund_usd —
    # same reuse as Task 2's deployment_fee_deducted/transfer_fee_deducted.
    shares_exchange_rate_ngn = Column(Numeric(20, 6), nullable=True)
    shares_price_per_share_ngn = Column(Numeric(20, 4), nullable=True)
    net_ngn = Column(Numeric(20, 2), nullable=True)

    # DPRP oversubscription pro-rata: the slice of this investment's net principal that was
    # NOT deployed into shares because the batch's fund had a hard cap on what could actually
    # be purchased (see is_dangote_dprp_fund). Set once, at deployment time, to
    # pre_refund_net_principal * (1 - allocation_rate). Zero for every non-oversubscribed
    # investment (the overwhelming majority) — net_principal below is unchanged in that case.
    oversubscription_refund_amount = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))

    # Removed Composite unique constraint: internal_client_code + batch_id must be unique

    # Relationships
    batch = db.relationship('Batch', back_populates='investments')
    fund = db.relationship('CoreFund', backref='investments')
    share_class = db.relationship('ShareClass', foreign_keys=[share_class_id], uselist=False, backref=db.backref('investments', lazy='dynamic'))

    @property
    def net_principal(self):
        """
        Calculate the current net principal after all deductions.

        For a DPRP investment affected by oversubscription pro-rata allocation,
        this also subtracts oversubscription_refund_amount — every downstream
        consumer of net_principal (shares calc at deployment, opening_balance in
        the valuation cascade, statements, portfolio displays) already reads this
        property, so reducing it here is what makes the deployed amount the SSOT
        everywhere without having to touch each call site individually.
        """
        return (
            self.amount_deposited
            - self.transfer_fee_deducted
            - self.deployment_fee_deducted
            - (self.oversubscription_refund_amount or Decimal("0.00"))
        )

    @property
    def current_calculated_value(self):
        """Calculate current market value using shares × current NAV."""
        if self.shares_owned and self.share_class and self.share_class.current_nav:
            return self.shares_owned * self.share_class.current_nav
        return None

    @property
    def variance(self):
        """Calculate variance between official receipt value and calculated value."""
        if self.official_receipt_value and self.current_calculated_value:
            return self.official_receipt_value - self.current_calculated_value
        return None

    def __repr__(self):
        return f'<Investment {self.investor_name} ({self.internal_client_code}) - Fund: {self.fund_name} - {self.amount_deposited}>'

    @staticmethod
    def currency_from_share_series(share_series):
        raw = (share_series or "").strip().upper()
        if "KES" in raw:
            return "KES"
        return "USD"


@event.listens_for(Investment, "before_insert")
def _inherit_product_type_from_batch(mapper, connection, target):
    """
    A deposit/holding always takes its product_type from its batch — this is
    what makes the column a reliable filter/index instead of a second,
    independently-settable source of truth that could drift from the batch it
    lives in. Only runs at creation: batch_id is never reassigned after a
    deposit exists today, so there is no update-time case to cover, and adding
    one would mean a per-row SELECT on every ORM update — exactly what
    bulk_update_mappings elsewhere in this codebase was written to avoid.

    Covers every ORM creation path (manual add, Excel upload, tests, ...)
    automatically. Raw Core `insert()` statements (the high-volume bulk-upload
    path) bypass mapper events entirely and must set product_type explicitly —
    see app/BulkUpload/route.py.
    """
    if target.batch_id is None:
        return
    row = connection.execute(
        text("SELECT product_type FROM batches WHERE id = :batch_id"),
        {"batch_id": target.batch_id},
    ).first()
    if row is None:
        return
    batch_product_type = row[0]
    if target.product_type and target.product_type != batch_product_type:
        raise ValueError(
            f"Cannot save a {target.product_type} deposit into batch {target.batch_id}, "
            f"which is a {batch_product_type} batch."
        )
    target.product_type = batch_product_type


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
    status = Column(String(20), nullable=False, default='Pending_Confirmation')  # Pending_Confirmation/Queued/Confirmed/Failed/Suppressed
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    recipient_email = Column(String(100), nullable=False)
    recipient_name = Column(String(100), nullable=True)
    amount = Column(Numeric(20, 2), nullable=True)  # For deposit/withdrawal amounts
    fund_name = Column(String(100), nullable=True)
    batch_name = Column(String(100), nullable=True)
    currency_type = Column(String(10), nullable=True, default='USD')  # USD, KES, etc
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True), nullable=True)
    queued_at = Column(DateTime(timezone=True), nullable=True, index=True)  # set when an admin approves; the send queue drains oldest queued_at first
    trigger_source = Column(String(120), nullable=True, index=True)
    # INVESTOR_STATEMENT scope: comma-separated CoreFund ids this statement was
    # queued for, or NULL for a full consolidated statement. Read back by
    # _send_pending_email_now to attach the matching PDF at send time.
    statement_fund_ids = Column(String(255), nullable=True)

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

# Withdrawal.source values — distinguishes an investor-initiated withdrawal request from a
# DPRP oversubscription pro-rata refund queued automatically at deployment time. Both go
# through the exact same Pending -> Approved/Rejected flow and UI; `source` only affects
# filtering/labeling and (critically) is used to EXCLUDE oversubscription refunds from the
# many balance/aggregate queries that sum FINAL_WITHDRAWAL_STATUSES withdrawals — that money
# was never actually deployed into the fund (Investment.net_principal already reflects the
# reduction via oversubscription_refund_amount), so subtracting it again once the refund is
# approved would double-count it.
WITHDRAWAL_SOURCE_INVESTOR_REQUEST = "investor_request"
WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND = "oversubscription_refund"


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
    gross_amount = Column(Numeric(20, 2), nullable=True)  # Amount before fees
    exit_fee_deducted = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # 2% fee if < 6 months
    amount = Column(Numeric(20, 2), nullable=False)  # Net amount to be paid out
    date_withdrawn = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    status = Column(String(20), nullable=False, default='Pending')  # Pending|Approved|Rejected
    approved_at = Column(DateTime, nullable=True)
    note = Column(String(255), nullable=True)
    # See WITHDRAWAL_SOURCE_* above. Defaults to investor_request so existing rows and every
    # normal withdrawal (upload, manual entry) are unaffected.
    source = Column(String(30), nullable=False, default=WITHDRAWAL_SOURCE_INVESTOR_REQUEST)

    # Optional linkage to a batch (if the withdrawal was initiated in a batch context)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=True)

    # Only meaningful for source=oversubscription_refund. NULL until the
    # one-time Oversubscription/Refund Notice (see
    # EmailService.send_oversubscription_refund_notices) has actually been
    # sent for this refund — what stops that notice from being
    # regenerated/resent on a later regular statement send or a repeat
    # deploy-trigger call for the same investor.
    oversubscription_notice_sent_at = Column(DateTime(timezone=True), nullable=True)

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


class PortfolioDisplayCache(Base, db.Model):
    """
    Pre-computed aggregations and display data for investor portfolio pages.
    
    This cache stores:
    - KPI totals (principal, balance, profit, percentage)
    - Batch breakdown summaries
    - Fund groupings
    - Holdings table data
    - Fund allocation data for charts
    
    Updated whenever portfolio data changes (investments, withdrawals, epochs).
    """
    __tablename__ = 'portfolio_display_cache'

    id = Column(Integer, primary_key=True)
    client_code = Column(String(50), nullable=False, unique=True, index=True)
    investor_name = Column(String(100), nullable=True)
    
    # KPI Totals
    total_principal = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    total_current_balance = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    total_profit = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    profit_percentage = Column(Numeric(10, 4), nullable=False, default=Decimal("0.0000"))
    profit_trend = Column(String(10), nullable=False, default="neutral")  # up, down, neutral
    unique_batches = Column(Integer, nullable=False, default=0)
    
    # Aggregated Data (JSON)
    batch_breakdown = Column(Text, nullable=True)  # Serialized JSON array
    funds_grouped = Column(Text, nullable=True)  # Serialized JSON object
    holdings_display = Column(Text, nullable=True)  # Serialized JSON array for table
    fund_allocation = Column(Text, nullable=True)  # Serialized JSON array for chart
    
    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<PortfolioDisplayCache {self.client_code} - balance={self.total_current_balance}>"
