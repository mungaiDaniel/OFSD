from sqlalchemy import Column, Integer, DateTime, Numeric, String, ForeignKey, UniqueConstraint, Index, Boolean
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class ValuationRun(Base, db.Model):
    """
    Idempotency + locking for global (core-fund) valuation commits.

    Prevents committing the same core_fund_id + epoch_end twice.
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

