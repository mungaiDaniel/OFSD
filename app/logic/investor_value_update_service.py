"""
Investor Value Update Service

Handles automatic updates to investor current values when NAV changes for a share class.
"""

from decimal import Decimal
from sqlalchemy import and_
from app.database.database import db
from app.Investments.model import Investment
from app.Funds.share_class import ShareClass


class InvestorValueUpdateService:
    """
    Service for updating investor current values when NAV changes.
    """

    @staticmethod
    def update_investor_values_for_share_class(share_class_id: int, new_nav: Decimal):
        """
        Update current_calculated_value for all investors holding shares in the given share class.

        Args:
            share_class_id: The share class ID
            new_nav: The new NAV per share
        """
        # Update the ShareClass current_nav
        share_class = db.session.query(ShareClass).filter(ShareClass.id == share_class_id).first()
        if not share_class:
            raise ValueError(f"Share class {share_class_id} not found")

        share_class.current_nav = new_nav

        # Update all investments with this share class
        investments = db.session.query(Investment).filter(
            and_(
                Investment.share_class_id == share_class_id,
                Investment.shares_owned.isnot(None),
                Investment.shares_owned > 0
            )
        ).all()

        updated_count = 0
        for investment in investments:
            if investment.shares_owned:
                # Calculate new current value: shares × new NAV
                new_value = investment.shares_owned * new_nav
                investment.current_market_value = new_value
                updated_count += 1

        db.session.commit()

        return {
            "share_class_id": share_class_id,
            "new_nav": float(new_nav),
            "investments_updated": updated_count
        }