from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, Boolean, Index, Numeric
from sqlalchemy.orm import relationship
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class InvestorShares(Base, db.Model):
    """
    Tracks individual investor share holdings across batches and share classes.
    
    This is the cornerstone of the share-based valuation model:
    - Stores the number of shares an investor owns in a share class
    - Records the deployment NAV (cost basis) at time of investment
    - Links to investment, share class, and batch for full context
    
    Formula Usage:
    - Current Market Value = shares_owned * latest_nav_for_share_class
    - Cost Basis = shares_owned * deployment_nav
    - Gain/Loss = Current Market Value - Cost Basis
    """

    __tablename__ = "investor_shares"

    id = Column(Integer, primary_key=True)
    investment_id = Column(
        Integer, ForeignKey("investments.id", ondelete="CASCADE"), nullable=False
    )
    share_class_id = Column(
        Integer, ForeignKey("share_classes.id", ondelete="CASCADE"), nullable=False
    )
    batch_id = Column(
        Integer, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    shares_owned = Column(Numeric(20, 6), nullable=False)
    deployment_nav = Column(Numeric(20, 6), nullable=False)
    deployment_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_investor_shares_investment_id", "investment_id"),
        Index("ix_investor_shares_share_class_id", "share_class_id"),
        Index("ix_investor_shares_batch_id", "batch_id"),
        Index("ix_investor_shares_active", "is_active"),
    )

    investment = relationship("Investment", foreign_keys=[investment_id], uselist=False, backref=db.backref("investor_shares", lazy="dynamic"))
    batch = relationship("Batch", foreign_keys=[batch_id], uselist=False, backref=db.backref("investor_shares", lazy="dynamic"))
    share_class = relationship("ShareClass", foreign_keys=[share_class_id], uselist=False, backref=db.backref("investor_shares", lazy="dynamic"))

    def __repr__(self):
        return f"<InvestorShares inv={self.investment_id} shares={self.shares_owned} class={self.share_class_id} batch={self.batch_id}>"

    def __str__(self):
        return f"{self.shares_owned} shares @ {self.deployment_nav} NAV (deployed {self.deployment_date})"

    def calculate_cost_basis(self):
        """
        Returns the cost basis (investment amount) based on deployment NAV.
        
        Returns:
            Decimal: shares_owned * deployment_nav
        """
        return Decimal(self.shares_owned) * Decimal(self.deployment_nav)

    def calculate_market_value(self, current_nav):
        """
        Calculates current market value based on latest NAV.
        
        Args:
            current_nav: Current NAV per share (Decimal or Numeric)
        
        Returns:
            Decimal: shares_owned * current_nav
        """
        return Decimal(self.shares_owned) * Decimal(current_nav)

    def calculate_gain_loss(self, current_nav):
        """
        Calculates unrealized gain/loss.
        
        Args:
            current_nav: Current NAV per share (Decimal or Numeric)
        
        Returns:
            Decimal: market_value - cost_basis
        """
        market_value = self.calculate_market_value(current_nav)
        cost_basis = self.calculate_cost_basis()
        return market_value - cost_basis

    def calculate_performance_percentage(self, current_nav):
        """
        Calculates performance as a percentage.
        
        Args:
            current_nav: Current NAV per share (Decimal or Numeric)
        
        Returns:
            Decimal: ((current_nav / deployment_nav) - 1) * 100
        """
        if Decimal(self.deployment_nav) == 0:
            return Decimal("0.00")
        
        nav_ratio = Decimal(current_nav) / Decimal(self.deployment_nav)
        return ((nav_ratio - 1) * 100).quantize(Decimal("0.01"))
