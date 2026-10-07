from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, Index, CheckConstraint, Numeric
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class NavHistory(Base, db.Model):
    """
    Stores historical NAV prices per share class and date.
    
    Enables the engine to:
    1. Fetch the latest NAV for a given share class
    2. Retrieve NAV at a specific date for historical statements
    3. Track NAV source (deployment vs valuation-derived)
    
    Constraints:
    - (share_class_id, nav_date, source) is UNIQUE → one NAV per date per source type
    - source must be either 'deployment' or 'valuation' → enforces valid source types
    """

    __tablename__ = "nav_history"

    id = Column(Integer, primary_key=True)
    share_class_id = Column(
        Integer, ForeignKey("share_classes.id", ondelete="CASCADE"), nullable=False
    )
    nav_date = Column(Date, nullable=False)
    nav_per_share = Column(Numeric(20, 6), nullable=False)
    total_fund_nav = Column(Numeric(20, 2), nullable=True)
    source = Column(String(20), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "share_class_id",
            "nav_date",
            "source",
            name="_nav_history_class_date_source_uc",
        ),
        CheckConstraint(
            "source IN ('deployment', 'valuation')",
            name="_nav_source_check",
        ),
        Index("ix_nav_history_share_class_date", "share_class_id", "nav_date"),
        Index("ix_nav_history_date", "nav_date"),
        Index("ix_nav_history_source", "source"),
    )

    def __repr__(self):
        return f"<NavHistory class={self.share_class_id} date={self.nav_date} nav={self.nav_per_share} source={self.source}>"

    def __str__(self):
        return f"NAV {self.nav_per_share} on {self.nav_date} (source: {self.source})"

    @classmethod
    def get_latest_nav(cls, share_class_id, reference_date=None):
        """
        Fetch the most recent NAV for a share class up to and including reference_date.
        
        Args:
            share_class_id: ID of the share class
            reference_date: Date to fetch NAV for (defaults to today)
        
        Returns:
            NavHistory record with the latest NAV, or None if no record exists
        """
        from sqlalchemy import desc

        if reference_date is None:
            from datetime import date
            reference_date = date.today()

        return (
            cls.query.filter(
                cls.share_class_id == share_class_id, cls.nav_date <= reference_date
            )
            .order_by(desc(cls.nav_date))
            .first()
        )

    @classmethod
    def resolve_current_price(cls, share_class_id, deployment_date, deployment_nav, session=None):
        """
        Single source of truth for "current price per share" of a DEPLOYED
        position — used everywhere a screen needs to show a fund/batch's
        current value (Overview AUM, batch detail Total NAV, investor
        market value/performance, statement PDFs).

        Deployment never writes its own row into nav_history (only
        InvestorShares.deployment_nav records it) — so naively taking
        "whatever NavHistory row is newest for this share class" can return
        a valuation that's actually OLDER than this deployment (e.g. from a
        different, earlier-deployed batch on the same share class, or leftover
        test/seed data), silently substituting a stale price. That produced
        real, reported bugs: a batch deployed at NAV 55 showing a market value
        computed at NAV 45 everywhere (Overview AUM, batch detail, investor
        pages) because 45 happened to be the row `ORDER BY nav_date DESC`
        picked, with no check that it was ever dated after deployment.

        Rule: prefer the latest NavHistory row dated on/after deployment_date
        (a real valuation committed since this position was deployed). If
        none exists yet, this position hasn't been revalued since deployment,
        so its OWN deployment NAV is the current price — never an older,
        pre-deployment valuation.

        Returns (nav_per_share: Decimal, nav_date: date|None, is_deployment_fallback: bool).
        nav_per_share is None only if both deployment_date/deployment_nav are
        unavailable and no NavHistory row qualifies (nothing to fall back to).
        """
        from decimal import Decimal as _Decimal

        query_session = session or cls.query.session
        latest_nav = None
        if deployment_date is not None:
            latest_nav = (
                query_session.query(cls)
                .filter(cls.share_class_id == share_class_id, cls.nav_date >= deployment_date)
                .order_by(cls.nav_date.desc())
                .first()
            )
        if latest_nav is not None:
            return _Decimal(str(latest_nav.nav_per_share)), latest_nav.nav_date, False

        if deployment_nav is not None:
            return _Decimal(str(deployment_nav)), deployment_date, True

        return None, None, True

    @classmethod
    def get_nav_at_date(cls, share_class_id, nav_date, source=None):
        """
        Fetch the NAV for a specific share class on a specific date.
        
        Args:
            share_class_id: ID of the share class
            nav_date: Target date for NAV
            source: Optional filter for 'deployment' or 'valuation' source
        
        Returns:
            NavHistory record or None if not found
        """
        query = cls.query.filter(
            cls.share_class_id == share_class_id, cls.nav_date == nav_date
        )

        if source:
            query = query.filter(cls.source == source)

        return query.first()
