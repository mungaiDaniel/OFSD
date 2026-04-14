from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone


class CoreFund(Base, db.Model):
    """
    Core funds are the global buckets used for performance triggering:
    Axiom and Atium.
    """

    __tablename__ = "core_funds"

    id = Column(Integer, primary_key=True)
    fund_name = Column(String(100), nullable=False)
    fund_code = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("fund_name", name="_core_fund_name_uc"),
    )

    def __repr__(self):
        return f"<CoreFund {self.fund_name} active={self.is_active}>"

