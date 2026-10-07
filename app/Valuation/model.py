from sqlalchemy import Column, Integer, DateTime, Numeric, String, ForeignKey, UniqueConstraint, Index, Boolean, Text
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class ValuationRun(Base, db.Model):
    """
    Idempotency + locking for global (core-fund) valuation commits.

    Prevents committing the same core_fund_id + epoch_end twice.
    Tracks both fund-level and investor-level totals for reconciliation.
    """

    __tablename__ = "valuation_runs"

    id = Column(Integer, primary_key=True)
    core_fund_id = Column(Integer, ForeignKey("core_funds.id"), nullable=False)
    epoch_start = Column(DateTime, nullable=False)
    epoch_end = Column(DateTime, nullable=False)
    performance_rate = Column(Numeric(12, 8), nullable=False)
    head_office_total = Column(Numeric(20, 2), nullable=False)
    status = Column(String(20), nullable=False, default="Committed")  # Committed|Failed
    is_committed = Column(Boolean, nullable=False, default=True) # Explicit immutability flag
    
    # Dual-layer valuation totals
    total_fund_level_gain = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Sum of all fund-level gains
    total_investor_gains = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Sum of all investor-level gains
    total_unallocated_surplus = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Sum of all fund surpluses
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("core_fund_id", "epoch_end", name="_valuation_run_fund_end_uc"),
        Index("ix_valuation_runs_fund_end", "core_fund_id", "epoch_end"),
    )

    def __repr__(self):
        return f"<ValuationRun fund={self.core_fund_id} {self.epoch_start.date()}→{self.epoch_end.date()} status={self.status}>"


class Statement(Base, db.Model):
    """
    Stores committed valuation statements for reporting.

    One row per investor per fund per valuation run.
    Tracks both fund-level (full-month) and investor-level (pro-rata) earnings.
    """

    __tablename__ = "statements"

    id = Column(Integer, primary_key=True)
    investor_id = Column(Integer, ForeignKey("investments.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    fund_id = Column(Integer, ForeignKey("core_funds.id"), nullable=False)
    valuation_run_id = Column(Integer, ForeignKey("valuation_runs.id"), nullable=False)
    opening_balance = Column(Numeric(20, 2), nullable=False)
    withdrawals = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Amount withdrawn
    performance_gain = Column(Numeric(20, 2), nullable=False)
    closing_balance = Column(Numeric(20, 2), nullable=False)
    
    # Dual-layer valuation tracking
    fund_level_gain = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Full-month earnings at fund rate
    investor_level_gain = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Pro-rata earnings based on deployment
    fund_surplus = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Unallocated gain (fund_level - investor_level)
    
    # Active days tracking for pro-rata calculation
    days_active_in_period = Column(Integer, nullable=False, default=0)  # Days investor was active in this period
    period_total_days = Column(Integer, nullable=False, default=1)  # Total days in valuation period
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("investor_id", "fund_id", "valuation_run_id", name="_statement_investor_fund_run_uc"),
        Index("ix_statements_investor_batch", "investor_id", "batch_id"),
        Index("ix_statements_fund_run", "fund_id", "valuation_run_id"),
    )

    # Relationships
    investor = db.relationship("Investment", backref="statements")
    batch = db.relationship("Batch", backref="statements")
    fund = db.relationship("CoreFund", backref="statements")
    valuation_run = db.relationship("ValuationRun", backref="statements")

    def __repr__(self):
        return f"<Statement investor={self.investor_id} fund={self.fund_id} closing={self.closing_balance}>"


class BatchValuation(Base, db.Model):
    """
    Batch-level valuation tracking for atomic batch calculations.
    
    Stores per-batch balance history with period end dates.
    Dashboard aggregates most recent balance per batch.
    """

    __tablename__ = "batch_valuations"

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    period_end_date = Column(DateTime(timezone=True), nullable=False)
    balance_at_end_of_period = Column(Numeric(20, 2), nullable=False)
    performance_rate = Column(Numeric(12, 8), nullable=False)  # Rate used for this period
    total_principal = Column(Numeric(20, 2), nullable=False)  # Net principal at start of period
    total_profit = Column(Numeric(20, 2), nullable=False)  # Profit earned in this period
    total_withdrawals = Column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))  # Withdrawals in this period
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("batch_id", "period_end_date", name="_batch_valuation_batch_period_uc"),
        Index("ix_batch_valuations_batch_period", "batch_id", "period_end_date"),
    )

    # Relationships
    batch = db.relationship("Batch", backref="batch_valuations")

    def __repr__(self):
        return f"<BatchValuation batch={self.batch_id} period_end={self.period_end_date.date()} balance={self.balance_at_end_of_period}>"


class InvestmentBatchValuation(Base, db.Model):
    """
    Per-investment, per-batch valuation snapshots. Atomic batch runs only write rows
    for investments in that batch; other batches are never touched.
    """

    __tablename__ = "investment_batch_valuations"

    id = Column(Integer, primary_key=True)
    investment_id = Column(Integer, ForeignKey("investments.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    period_end_date = Column(DateTime(timezone=True), nullable=False)
    balance_at_end_of_period = Column(Numeric(20, 2), nullable=False)
    net_principal_snapshot = Column(Numeric(20, 2), nullable=False)
    nav_at_period_end = Column(Numeric(24, 8), nullable=True)
    total_shares_at_time = Column(Numeric(24, 8), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("investment_id", "period_end_date", name="_inv_batch_val_investor_period_uc"),
        Index("ix_inv_batch_val_batch_period", "batch_id", "period_end_date"),
    )

    investment = db.relationship("Investment", backref="batch_valuation_snapshots")
    batch = db.relationship("Batch", backref="investment_batch_valuations")

    def __repr__(self):
        return (
            f"<InvestmentBatchValuation inv={self.investment_id} batch={self.batch_id} "
            f"period_end={self.period_end_date.date()} balance={self.balance_at_end_of_period}>"
        )


class DailyNAV(Base, db.Model):
    __tablename__ = "daily_nav"

    id = Column(Integer, primary_key=True)
    nav_date = Column(DateTime(timezone=True), nullable=False)
    share_series = Column(String(100), nullable=False)
    nav_price = Column(Numeric(24, 8), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("nav_date", "share_series", name="_daily_nav_date_series_uc"),
        Index("ix_daily_nav_series_date", "share_series", "nav_date"),
    )


class ValuationJob(Base, db.Model):
    """
    Tracks a NAV valuation commit (POST /api/v1/valuation/nav, dry_run=False)
    that runs as a background job instead of inline in the request — same
    reasoning and shape as app/BulkUpload/model.py's BulkUploadJob: at 100k+
    investors, one HTTP request holding open a ValuationSnapshot-per-investor
    write loop is what made "commit valuation" hang/not load. See
    app/Valuation/route.py's nav_valuation()/_run_valuation_commit_job() for
    how this gets driven.

    status: 'queued' -> 'running' -> 'completed' | 'failed'
    request_payload holds the exact request body (valuation_date + classes)
    so the background worker has everything it needs without the request
    that created the job still being open.
    """

    __tablename__ = "valuation_jobs"

    id = Column(Integer, primary_key=True)
    status = Column(String(20), nullable=False, default="queued")

    total_investors = Column(Integer, nullable=False, default=0)
    processed_investors = Column(Integer, nullable=False, default=0)
    snapshots_created = Column(Integer, nullable=False, default=0)

    request_payload = Column(Text, nullable=False)
    results_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, nullable=True)
    created_by_email = Column(String(120), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<ValuationJob {self.id} {self.status} {self.processed_investors}/{self.total_investors}>"

