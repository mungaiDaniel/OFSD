from sqlalchemy import Column, Integer, DateTime, Numeric, String, ForeignKey, UniqueConstraint, Index
from app.database.database import db
from base_model import Base
from datetime import datetime


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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("core_fund_id", "epoch_end", name="_valuation_run_fund_end_uc"),
        Index("ix_valuation_runs_fund_end", "core_fund_id", "epoch_end"),
    )

    def __repr__(self):
        return f"<ValuationRun fund={self.core_fund_id} {self.epoch_start.date()}→{self.epoch_end.date()} status={self.status}>"

