"""
Daily Activity report — status column
=============================================================================
Deposits used to always say "Completed" and valuations "Committed", which
read like two competing states of the same thing. A deposit's status is now
the stage its batch has actually reached; a valuation row says "Valued".

Run with: pytest tests/test_daily_activity_status.py -v
"""

from datetime import date, datetime, timezone

import pytest
from decimal import Decimal

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Batch.model import Batch, deposit_status_label
from app.Investments.model import Investment


def test_deposit_status_label_maps_every_stage():
    assert [deposit_status_label(s) for s in (1, 2, 3, 4)] == ["Deposited", "Transferred", "Deployed", "Active"]
    assert deposit_status_label(None) == "Deposited"


@pytest.mark.unit
def test_daily_activity_deposit_status_follows_batch_stage(app):
    from app.Reports.route import _gather_daily_activity

    with app.app_context():
        fund = CoreFund(fund_name="Status Fund", fund_code="STAT-F")
        db.session.add(fund)
        db.session.flush()
        share_class = ShareClass(core_fund_id=fund.id, class_name="Status Class", class_code="STAT-I", currency="USD")
        db.session.add(share_class)
        db.session.flush()

        deposited_at = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        for stage, code in ((1, "S1"), (2, "S2"), (4, "S4")):
            batch = Batch(batch_name=f"Status Batch {stage}", share_class_id=share_class.id, stage=stage, is_active=True)
            db.session.add(batch)
            db.session.flush()
            db.session.add(Investment(
                investor_name=f"Investor {code}", investor_email=f"{code}@example.com", internal_client_code=code,
                amount_deposited=Decimal("1000.00"), batch_id=batch.id, fund_id=fund.id,
                share_class_id=share_class.id, date_deposited=deposited_at,
            ))
        db.session.commit()

        data = _gather_daily_activity(date(2026, 10, 1), datetime(2026, 10, 1, 23, 59, tzinfo=timezone.utc))
        statuses = {e["internal_client_code"]: e["status"] for e in data["events"] if e["type"] == "deposit"}
        assert statuses == {"S1": "Deposited", "S2": "Transferred", "S4": "Active"}
        assert "Completed" not in statuses.values()
