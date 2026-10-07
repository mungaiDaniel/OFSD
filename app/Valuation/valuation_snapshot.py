from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, UniqueConstraint, Index, Numeric, desc
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone, date
from decimal import Decimal


class ValuationSnapshot(Base, db.Model):
    """
    Point-in-time valuation record for an investor's share holding.
    
    This is the "Golden Source" for historical statements:
    - Captures NAV, share count, market value, and performance at a specific date
    - Once created, should be treated as immutable (for audit/reporting integrity)
    - Enables reconciliation and historical reporting
    - Supports the "locked statement" model where historical data cannot be altered
    
    Example Record:
    - investor_shares_id=1 (Joy Kendi's Class I-KES holding)
    - valuation_date=2026-04-10
    - nav_per_share=1389.5737
    - shares_held=771.92
    - market_value=1,072,636.69
    - performance_pct=4.52
    """

    __tablename__ = "valuation_snapshots"

    id = Column(Integer, primary_key=True)
    investor_shares_id = Column(
        Integer, ForeignKey("investor_shares.id", ondelete="CASCADE"), nullable=False
    )
    valuation_date = Column(Date, nullable=False)
    nav_per_share = Column(Numeric(20, 6), nullable=False)
    shares_held = Column(Numeric(20, 6), nullable=False)
    market_value = Column(Numeric(20, 2), nullable=False)
    performance_pct = Column(Numeric(10, 4), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "investor_shares_id",
            "valuation_date",
            name="_valuation_snapshots_shares_date_uc",
        ),
        Index("ix_valuation_snapshots_valuation_date", "valuation_date"),
        Index("ix_valuation_snapshots_investor_shares_id", "investor_shares_id"),
    )

    def __repr__(self):
        return f"<ValuationSnapshot shares={self.investor_shares_id} date={self.valuation_date} mv={self.market_value} perf={self.performance_pct}%>"

    def __str__(self):
        return f"Snapshot {self.valuation_date}: {self.shares_held} shares @ {self.nav_per_share} NAV = ${self.market_value:,.2f} ({self.performance_pct}% return)"

    @classmethod
    def get_latest_snapshot(cls, investor_shares_id, reference_date=None):
        """
        Fetch the most recent valuation snapshot for a holding up to and including reference_date.
        
        Args:
            investor_shares_id: ID of the investor_shares record
            reference_date: Date to fetch snapshot for (defaults to today)
        
        Returns:
            ValuationSnapshot record with the latest valuation, or None if no records exist
        """
        if reference_date is None:
            reference_date = date.today()

        return (
            cls.query.filter(
                cls.investor_shares_id == investor_shares_id,
                cls.valuation_date <= reference_date,
            )
            .order_by(desc(cls.valuation_date))
            .first()
        )

    @classmethod
    def get_snapshot_at_date(cls, investor_shares_id, valuation_date):
        """
        Fetch the exact valuation snapshot for a holding at a specific date.
        
        Args:
            investor_shares_id: ID of the investor_shares record
            valuation_date: Target valuation date
        
        Returns:
            ValuationSnapshot record or None if not found
        """
        return cls.query.filter(
            cls.investor_shares_id == investor_shares_id,
            cls.valuation_date == valuation_date,
        ).first()

    @classmethod
    def get_historical_snapshots(cls, investor_shares_id, start_date=None, end_date=None):
        """
        Fetch all valuation snapshots for a holding within a date range.
        
        Args:
            investor_shares_id: ID of the investor_shares record
            start_date: Optional start date (inclusive)
            end_date: Optional end date (inclusive)
        
        Returns:
            List of ValuationSnapshot records ordered by date ascending
        """
        query = cls.query.filter(cls.investor_shares_id == investor_shares_id)

        if start_date:
            query = query.filter(cls.valuation_date >= start_date)

        if end_date:
            query = query.filter(cls.valuation_date <= end_date)

        return query.order_by(cls.valuation_date).all()

    @classmethod
    def get_month_snapshots(cls, valuation_date):
        """
        Fetch all valuation snapshots for a given month.
        
        Args:
            valuation_date: Any date within the target month
        
        Returns:
            List of ValuationSnapshot records for that month
        """
        from sqlalchemy import and_, extract

        year = valuation_date.year
        month = valuation_date.month

        return cls.query.filter(
            and_(
                extract("year", cls.valuation_date) == year,
                extract("month", cls.valuation_date) == month,
            )
        ).all()

    @classmethod
    def create_snapshot(cls, investor_shares_id, valuation_date, nav_per_share, shares_held, deployment_nav):
        """
        Factory method to create and validate a new valuation snapshot.
        
        Args:
            investor_shares_id: ID of the investor_shares record
            valuation_date: Date of valuation
            nav_per_share: Current NAV per share
            shares_held: Number of shares held
            deployment_nav: Original NAV at deployment (for performance calc)
        
        Returns:
            New ValuationSnapshot instance (not committed to DB)
        """
        nav_per_share = Decimal(str(nav_per_share))
        shares_held = Decimal(str(shares_held))
        deployment_nav = Decimal(str(deployment_nav))

        # Calculate market value
        market_value = (shares_held * nav_per_share).quantize(Decimal("0.01"))

        # Calculate performance percentage
        if deployment_nav == 0:
            performance_pct = Decimal("0.00")
        else:
            nav_ratio = nav_per_share / deployment_nav
            performance_pct = ((nav_ratio - 1) * 100).quantize(Decimal("0.0001"))

        return cls(
            investor_shares_id=investor_shares_id,
            valuation_date=valuation_date,
            nav_per_share=nav_per_share,
            shares_held=shares_held,
            market_value=market_value,
            performance_pct=performance_pct,
        )

    def calculate_change_from_previous(self, previous_snapshot):
        """
        Calculates the change in market value from a previous snapshot.
        
        Args:
            previous_snapshot: Previous ValuationSnapshot record
        
        Returns:
            dict with 'absolute_change' and 'percentage_change'
        """
        if not previous_snapshot:
            return None

        absolute_change = Decimal(self.market_value) - Decimal(previous_snapshot.market_value)
        
        if Decimal(previous_snapshot.market_value) == 0:
            percentage_change = Decimal("0.00")
        else:
            percentage_change = (
                (absolute_change / Decimal(previous_snapshot.market_value)) * 100
            ).quantize(Decimal("0.01"))

        return {
            "absolute_change": absolute_change,
            "percentage_change": percentage_change,
            "from_date": previous_snapshot.valuation_date,
            "to_date": self.valuation_date,
        }
