from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, CheckConstraint, Numeric, event, text
from app.database.database import db
from app.database.product_type import ProductTypeEnum, FUNDS
from base_model import Base
from datetime import datetime, timezone


class ShareClass(Base, db.Model):
    """
    Represents share series within a CoreFund.
    Each share class has a unique code and currency—enabling multi-currency funds
    to offer different share series (e.g., "Class I - KES", "Class I - USD").

    Constraints:
    - (core_fund_id, class_code) must be UNIQUE → enforces no duplicate classes per fund
    - currency must be one of: 'KES', 'USD', 'NGN' → enforces supported currencies only
      (NGN added for SHARES/DPRP — Task 7/8; Funds share classes stay KES/USD)

    product_type (Task 8) is inherited from core_fund_id's CoreFund at
    creation and validated to always match it — see
    _inherit_product_type_from_fund below. Never independently settable, same
    reasoning as Investment.product_type inheriting from its Batch.
    """

    __tablename__ = "share_classes"

    id = Column(Integer, primary_key=True)
    core_fund_id = Column(Integer, ForeignKey("core_funds.id"), nullable=False)
    class_name = Column(String(100), nullable=False)
    class_code = Column(String(20), nullable=False, unique=True)
    currency = Column(String(3), nullable=False)
    product_type = Column(ProductTypeEnum, nullable=False, default=FUNDS, server_default=FUNDS)
    is_active = Column(Boolean, default=True, nullable=False)
    current_nav = Column(Numeric(20, 6), nullable=True)  # Current NAV per share for this class
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("core_fund_id", "class_code", name="_share_classes_fund_code_uc"),
        CheckConstraint("currency IN ('KES', 'USD', 'NGN')", name="_currency_check"),
        Index("ix_share_classes_fund_id", "core_fund_id"),
        Index("ix_share_classes_active", "is_active"),
        Index("ix_share_classes_product_type", "product_type"),
    )

    def __repr__(self):
        return f"<ShareClass {self.class_code} ({self.currency}) fund={self.core_fund_id} product={self.product_type} active={self.is_active}>"

    def __str__(self):
        return f"{self.class_name} ({self.class_code}) - {self.currency}"


@event.listens_for(ShareClass, "before_insert")
def _inherit_product_type_from_fund(mapper, connection, target):
    """
    Task 8: a share class always takes its product_type from its CoreFund —
    mirrors Investment._inherit_product_type_from_batch exactly (same
    reasoning: a denormalized column that's a reliable filter/index only if
    it can never independently drift from its parent). Only runs at
    creation: core_fund_id is never reassigned after a share class exists.
    """
    if target.core_fund_id is None:
        return
    row = connection.execute(
        text("SELECT product_type FROM core_funds WHERE id = :core_fund_id"),
        {"core_fund_id": target.core_fund_id},
    ).first()
    if row is None:
        return
    fund_product_type = row[0]
    if target.product_type and target.product_type != fund_product_type:
        raise ValueError(
            f"Cannot create a {target.product_type} share class under fund {target.core_fund_id}, "
            f"which is a {fund_product_type} fund."
        )
    target.product_type = fund_product_type
