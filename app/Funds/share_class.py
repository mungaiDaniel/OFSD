from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, CheckConstraint, Numeric
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone


class ShareClass(Base, db.Model):
    """
    Represents share series within a CoreFund.
    Each share class has a unique code and currency—enabling multi-currency funds
    to offer different share series (e.g., "Class I - KES", "Class I - USD").

    Constraints:
    - (core_fund_id, class_code) must be UNIQUE → enforces no duplicate classes per fund
    - currency must be one of: 'KES', 'USD'  → enforces supported currencies only
    """

    __tablename__ = "share_classes"

    id = Column(Integer, primary_key=True)
    core_fund_id = Column(Integer, ForeignKey("core_funds.id"), nullable=False)
    class_name = Column(String(100), nullable=False)
    class_code = Column(String(20), nullable=False, unique=True)
    currency = Column(String(3), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    current_nav = Column(Numeric(20, 6), nullable=True)  # Current NAV per share for this class
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("core_fund_id", "class_code", name="_share_classes_fund_code_uc"),
        CheckConstraint("currency IN ('KES', 'USD')", name="_currency_check"),
        Index("ix_share_classes_fund_id", "core_fund_id"),
        Index("ix_share_classes_active", "is_active"),
    )

    def __repr__(self):
        return f"<ShareClass {self.class_code} ({self.currency}) fund={self.core_fund_id} active={self.is_active}>"

    def __str__(self):
        return f"{self.class_name} ({self.class_code}) - {self.currency}"
