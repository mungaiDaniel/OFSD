"""
NAV-Based Portfolio Valuation Service

Implements share-based valuations using NAV (Net Asset Value) instead of percentages.
This aligns with the Mauritius Head Office model where each investor holds shares
in a specific share class, and valuations are derived from NAV per share.

Core Logic:
1. Accept valuation_date and list of (share_class_id, nav_per_share, total_fund_nav)
2. For each share class, load all active investor_shares records
3. Validate system_total = sum(shares_owned) * nav_per_share ≈ total_fund_nav
4. Calculate market value and performance for each holding
5. Persist valuation snapshots and nav history
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import List, NamedTuple, Dict, Tuple
import logging

from sqlalchemy import and_

from app.database.database import db
from app.Funds.share_class import ShareClass
from app.Funds.investor_shares import InvestorShares
from app.Investments.model import Investment
from app.Funds.nav_history import NavHistory
from app.Valuation.valuation_snapshot import ValuationSnapshot

logger = logging.getLogger(__name__)


# Configuration constants
RECONCILIATION_TOLERANCE = Decimal("1.00")  # $1.00 tolerance for NAV reconciliation
NAV_DECIMAL_PLACES = 6
MARKET_VALUE_DECIMAL_PLACES = 2


class NavInput(NamedTuple):
    """Input NAV data for a single share class."""
    share_class_id: int
    nav_per_share: Decimal
    total_fund_nav: Decimal


class ValuationResult(NamedTuple):
    """Result of a valuation run."""
    valuation_date: date
    share_class_id: int
    nav_per_share: Decimal
    total_fund_nav: Decimal
    system_total: Decimal
    reconciliation_diff: Decimal
    snapshots_created: int
    nav_history_created: bool


class PortfolioValuationService:
    """
    Service for NAV-based portfolio valuations.
    
    Replaces the old percentage-based system with NAV calculations:
    - Market Value = Shares Owned × NAV Per Share
    - Performance % = ((Current NAV - Deployment NAV) / Deployment NAV) × 100
    - Reconciliation: System Total ≈ Total Fund NAV (within tolerance)
    """

    @staticmethod
    def _to_decimal(value) -> Decimal:
        """Safely convert value to Decimal."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _quantize_nav(value: Decimal) -> Decimal:
        """Quantize to NAV precision (6 decimal places)."""
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return value.quantize(Decimal(10) ** -NAV_DECIMAL_PLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def _quantize_money(value: Decimal) -> Decimal:
        """Quantize to money precision (2 decimal places)."""
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def validate_nav_inputs(nav_inputs: List[NavInput]) -> bool:
        """
        Validate NAV input data structure.
        
        Args:
            nav_inputs: List of NavInput tuples
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        if not nav_inputs:
            raise ValueError("NAV inputs list cannot be empty")

        class_ids = set()
        for nav_input in nav_inputs:
            if nav_input.share_class_id <= 0:
                raise ValueError(f"Invalid share_class_id: {nav_input.share_class_id}")
            if nav_input.share_class_id in class_ids:
                raise ValueError(f"Duplicate share_class_id: {nav_input.share_class_id}")
            class_ids.add(nav_input.share_class_id)

            if nav_input.nav_per_share <= 0:
                raise ValueError(
                    f"NAV per share must be positive for class {nav_input.share_class_id}"
                )
            if nav_input.total_fund_nav < 0:
                raise ValueError(
                    f"Total fund NAV cannot be negative for class {nav_input.share_class_id}"
                )

        return True

    @staticmethod
    def execute_valuation(
        valuation_date: date,
        nav_inputs: List[NavInput],
        dry_run: bool = False,
    ) -> List[ValuationResult]:
        """
        Execute NAV-based portfolio valuation for all share classes.
        
        Args:
            valuation_date: Date of valuation
            nav_inputs: List of NavInput with share class NAV data
            dry_run: If True, validate but don't persist to database
        
        Returns:
            List of ValuationResult for each share class
        
        Raises:
            ValueError: If validation fails or reconciliation exceeds tolerance
        """
        # Validate inputs
        PortfolioValuationService.validate_nav_inputs(nav_inputs)

        results = []

        for nav_input in nav_inputs:
            result = PortfolioValuationService._process_share_class_valuation(
                valuation_date=valuation_date,
                nav_input=nav_input,
                dry_run=dry_run,
            )
            results.append(result)

        return results

    @staticmethod
    def run_valuation(
        valuation_date: date,
        nav_inputs: List[NavInput],
        db_session=None,
    ) -> List[ValuationResult]:
        """
        Backwards-compatible alias for execute_valuation.
        """
        return PortfolioValuationService.execute_valuation(
            valuation_date=valuation_date,
            nav_inputs=nav_inputs,
            dry_run=False,
        )

    @staticmethod
    def _process_share_class_valuation(
        valuation_date: date,
        nav_input: NavInput,
        dry_run: bool = False,
    ) -> ValuationResult:
        """
        Process valuation for a single share class.
        
        Steps:
        1. Load all active investor_shares for this class
        2. Calculate system total = sum(shares) * nav_per_share
        3. Validate system total ≈ total_fund_nav (within tolerance)
        4. For each investor: create valuation snapshot
        5. Create nav_history record
        
        Args:
            valuation_date: Date of valuation
            nav_input: NavInput for this class
            dry_run: If True, don't persist to database
        
        Returns:
            ValuationResult with counts and reconciliation info
        """
        share_class_id = nav_input.share_class_id
        nav_per_share = PortfolioValuationService._quantize_nav(nav_input.nav_per_share)
        total_fund_nav = PortfolioValuationService._quantize_money(nav_input.total_fund_nav)

        # Load all active investor_shares for this class.
        # Use the current Investment.share_class_id mapping so that
        # any recent updates to Investment.share_class_id are reflected
        # in valuation even if InvestorShares.share_class_id is stale.
        investor_shares_list = (
            db.session.query(InvestorShares)
            .join(Investment, InvestorShares.investment_id == Investment.id)
            .filter(
                Investment.share_class_id == share_class_id,
                InvestorShares.is_active == True,
            )
            .all()
        )

        logger.info(
            f"Processing {len(investor_shares_list)} holdings for "
            f"share class {share_class_id} on {valuation_date}"
        )

        # Calculate system total
        system_total = Decimal("0")
        for inv_shares in investor_shares_list:
            shares = PortfolioValuationService._to_decimal(inv_shares.shares_owned)
            contribution = shares * nav_per_share
            system_total += contribution

        system_total = PortfolioValuationService._quantize_money(system_total)

        # Validate reconciliation
        reconciliation_diff = abs(system_total - total_fund_nav)
        if reconciliation_diff > RECONCILIATION_TOLERANCE:
            raise ValueError(
                f"Reconciliation failed for share class {share_class_id}: "
                f"System total ${system_total} vs Fund NAV ${total_fund_nav} "
                f"(diff: ${reconciliation_diff}, tolerance: ${RECONCILIATION_TOLERANCE})"
            )

        logger.info(
            f"Reconciliation passed: system_total=${system_total} vs "
            f"fund_nav=${total_fund_nav} (diff=${reconciliation_diff})"
        )

        # Create valuation snapshots for each investor holding
        snapshots_created = 0
        for inv_shares in investor_shares_list:
            snapshot = PortfolioValuationService._create_valuation_snapshot(
                investor_shares=inv_shares,
                valuation_date=valuation_date,
                nav_per_share=nav_per_share,
                dry_run=dry_run,
            )
            if snapshot and not dry_run:
                db.session.add(snapshot)
                snapshots_created += 1

        # Create nav_history record
        nav_history_created = PortfolioValuationService._create_nav_history(
            share_class_id=share_class_id,
            valuation_date=valuation_date,
            nav_per_share=nav_per_share,
            total_fund_nav=total_fund_nav,
            dry_run=dry_run,
        )

        # Commit all changes
        if not dry_run:
            db.session.commit()
            logger.info(
                f"Committed {snapshots_created} snapshots and nav_history for "
                f"class {share_class_id}"
            )

        return ValuationResult(
            valuation_date=valuation_date,
            share_class_id=share_class_id,
            nav_per_share=nav_per_share,
            total_fund_nav=total_fund_nav,
            system_total=system_total,
            reconciliation_diff=reconciliation_diff,
            snapshots_created=snapshots_created,
            nav_history_created=nav_history_created,
        )

    @staticmethod
    def _create_valuation_snapshot(
        investor_shares: InvestorShares,
        valuation_date: date,
        nav_per_share: Decimal,
        dry_run: bool = False,
    ) -> ValuationSnapshot | None:
        """
        Create a valuation snapshot for an investor holding.
        
        Calculates:
        - Market Value = Shares Held × NAV Per Share
        - Performance % = ((NAV Per Share - Deployment NAV) / Deployment NAV) × 100
        
        Args:
            investor_shares: InvestorShares record
            valuation_date: Date of valuation
            nav_per_share: Current NAV per share
            dry_run: If True, don't persist to database
        
        Returns:
            ValuationSnapshot instance (or None if it already exists)
        """
        # Check if snapshot already exists for this date
        existing = ValuationSnapshot.get_snapshot_at_date(
            investor_shares_id=investor_shares.id,
            valuation_date=valuation_date,
        )
        if existing:
            logger.debug(
                f"Snapshot already exists for investor_shares {investor_shares.id} "
                f"on {valuation_date}"
            )
            return None

        # Use factory method to create snapshot with automatic calculations
        try:
            snapshot = ValuationSnapshot.create_snapshot(
                investor_shares_id=investor_shares.id,
                valuation_date=valuation_date,
                nav_per_share=nav_per_share,
                shares_held=investor_shares.shares_owned,
                deployment_nav=investor_shares.deployment_nav,
            )
            logger.debug(
                f"Created snapshot: {snapshot.investor_shares_id} "
                f"market_value=${snapshot.market_value} "
                f"performance={snapshot.performance_pct}%"
            )
            return snapshot
        except Exception as e:
            logger.error(
                f"Failed to create snapshot for investor_shares {investor_shares.id}: {str(e)}"
            )
            if not dry_run:
                raise

    @staticmethod
    def _create_nav_history(
        share_class_id: int,
        valuation_date: date,
        nav_per_share: Decimal,
        total_fund_nav: Decimal,
        dry_run: bool = False,
    ) -> bool:
        """
        Create or update NAV history record for a share class.
        
        Args:
            share_class_id: ID of the share class
            valuation_date: Date of valuation
            nav_per_share: NAV per share
            total_fund_nav: Total fund NAV
            dry_run: If True, don't persist to database
        
        Returns:
            True if created/updated, False if already exists
        """
        # Check if nav_history already exists for this date/class/source combination
        existing = NavHistory.get_nav_at_date(
            share_class_id=share_class_id,
            nav_date=valuation_date,
            source="valuation",
        )
        if existing:
            logger.debug(
                f"NAV history already exists for class {share_class_id} on {valuation_date}"
            )
            return False

        # Create new nav_history record
        nav_hist = NavHistory(
            share_class_id=share_class_id,
            nav_date=valuation_date,
            nav_per_share=nav_per_share,
            total_fund_nav=total_fund_nav,
            source="valuation",
        )

        if not dry_run:
            db.session.add(nav_hist)
            logger.debug(
                f"Created nav_history: class={share_class_id} date={valuation_date} "
                f"nav={nav_per_share} total={total_fund_nav}"
            )

        return True

    @staticmethod
    def get_current_portfolio_value(share_class_id: int) -> Dict:
        """
        Calculate current total portfolio value for a share class.
        
        Returns:
            dict with total_shares, latest_nav, total_market_value
        """
        # Get latest NAV
        latest_nav = NavHistory.get_latest_nav(share_class_id)
        if not latest_nav:
            return {
                "share_class_id": share_class_id,
                "total_shares": Decimal("0"),
                "latest_nav": None,
                "total_market_value": Decimal("0"),
                "error": "No NAV history found",
            }

        # Calculate total shares using Investment mapping to ensure we
        # reflect the most up-to-date share_class assignments.
        total_shares = db.session.query(
            db.func.coalesce(db.func.sum(InvestorShares.shares_owned), 0)
        ).join(Investment, InvestorShares.investment_id == Investment.id).filter(
            Investment.share_class_id == share_class_id,
            InvestorShares.is_active == True,
        ).scalar() or Decimal("0")

        total_shares = PortfolioValuationService._to_decimal(total_shares)
        nav_per_share = PortfolioValuationService._to_decimal(latest_nav.nav_per_share)
        total_market_value = PortfolioValuationService._quantize_money(
            total_shares * nav_per_share
        )

        return {
            "share_class_id": share_class_id,
            "total_shares": total_shares,
            "latest_nav": nav_per_share,
            "nav_date": latest_nav.nav_date,
            "total_market_value": total_market_value,
        }

    @staticmethod
    def get_investor_valuation(investor_shares_id: int) -> Dict:
        """
        Get current valuation for an investor holding.
        
        Returns:
            dict with current market value, performance, shares, etc.
        """
        inv_shares = InvestorShares.query.get(investor_shares_id)
        if not inv_shares:
            return {"error": "Investor shares not found"}

        # Get latest NAV for the share class
        latest_nav = NavHistory.get_latest_nav(inv_shares.share_class_id)
        if not latest_nav:
            return {
                "investor_shares_id": investor_shares_id,
                "error": "No NAV history found for share class",
            }

        shares = PortfolioValuationService._to_decimal(inv_shares.shares_owned)
        current_nav = PortfolioValuationService._to_decimal(latest_nav.nav_per_share)
        deployment_nav = PortfolioValuationService._to_decimal(inv_shares.deployment_nav)

        market_value = PortfolioValuationService._quantize_money(shares * current_nav)
        cost_basis = PortfolioValuationService._quantize_money(shares * deployment_nav)
        gain_loss = PortfolioValuationService._quantize_money(market_value - cost_basis)

        if deployment_nav > 0:
            performance_pct = PortfolioValuationService._quantize_nav(
                ((current_nav - deployment_nav) / deployment_nav) * 100
            )
        else:
            performance_pct = Decimal("0")

        return {
            "investor_shares_id": investor_shares_id,
            "shares_held": shares,
            "deployment_nav": deployment_nav,
            "current_nav": current_nav,
            "nav_date": latest_nav.nav_date,
            "market_value": market_value,
            "cost_basis": cost_basis,
            "gain_loss": gain_loss,
            "performance_pct": performance_pct,
        }
