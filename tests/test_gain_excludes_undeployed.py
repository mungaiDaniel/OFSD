"""
FUNDS Gain/Loss must ignore deposits that haven't been deployed yet
=============================================================================
Deposits in a batch that isn't deployed (stage 1/2) are in Net Holdings but
have no shares and no value in the NAV total yet. Gain/Loss used to be
total value - Net Holdings, so that undeployed money showed up as a loss —
the Overview USD card went negative while every fund page was positive.
Gain/Loss is now measured against deployed net principal only.

Run with: pytest tests/test_gain_excludes_undeployed.py -v
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.Funds.investor_shares import InvestorShares
from app.Funds.nav_history import NavHistory


def get_auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_class(fund_name, fund_code, class_code):
    fund = CoreFund(fund_name=fund_name, fund_code=fund_code)
    db.session.add(fund)
    db.session.flush()
    share_class = ShareClass(core_fund_id=fund.id, class_name=f"{fund_name} Class", class_code=class_code, currency="USD")
    db.session.add(share_class)
    db.session.flush()
    return fund, share_class


def _add_deployed_holding(share_class, code):
    # 10,000 deposited -> 100 shares at deployment NAV 100.
    batch = Batch(
        batch_name=f"{code} Deployed", share_class_id=share_class.id, stage=4, is_active=True,
        date_deployed=datetime.now(timezone.utc) - timedelta(days=30), deployment_nav=Decimal("100"),
    )
    db.session.add(batch)
    db.session.flush()
    inv = Investment(
        investor_name="Deployed Investor", investor_email="d@example.com", internal_client_code=f"{code}-D",
        amount_deposited=Decimal("10000.00"), batch_id=batch.id, share_class_id=share_class.id,
    )
    db.session.add(inv)
    db.session.flush()
    db.session.add(InvestorShares(
        investment_id=inv.id, share_class_id=share_class.id, batch_id=batch.id,
        shares_owned=Decimal("100"), deployment_nav=Decimal("100"),
        deployment_date=date.today() - timedelta(days=30),
    ))


def _add_undeployed_deposit(share_class, code, amount):
    batch = Batch(batch_name=f"{code} Pending", share_class_id=share_class.id, stage=2, is_active=True, is_transferred=True)
    db.session.add(batch)
    db.session.flush()
    db.session.add(Investment(
        investor_name="Pending Investor", investor_email="p@example.com", internal_client_code=f"{code}-P",
        amount_deposited=Decimal(amount), batch_id=batch.id, share_class_id=share_class.id,
    ))


@pytest.mark.unit
class TestGainExcludesUndeployedDeposits:
    def test_fund_gain_ignores_undeployed_batch_in_same_class(self, client, app):
        with app.app_context():
            fund, share_class = _make_class("Gain Test Fund", "GAIN-A", "GAIN-A-I")
            _add_deployed_holding(share_class, "GAIN-A")
            _add_undeployed_deposit(share_class, "GAIN-A", "5000.00")
            # Valued at 110 -> 100 shares = 11,000 vs 10,000 deployed -> +1,000.
            db.session.add(NavHistory(share_class_id=share_class.id, nav_date=date.today(), nav_per_share=Decimal("110"), source="valuation"))
            db.session.commit()

            funds = client.get("/api/v1/funds/summary").get_json()["data"]["funds"]
            f = next(x for x in funds if x["fund_code"] == "GAIN-A")
            assert f["totals_by_currency"]["USD"] == pytest.approx(11000.00)
            # Net Holdings still counts the pending 5,000 deposit...
            assert f["net_holdings_by_currency"]["USD"] == pytest.approx(15000.00)
            # ...but Gain/Loss doesn't treat it as a loss (was -4,000).
            assert f["gain_by_currency"]["USD"] == pytest.approx(1000.00)

    def test_overview_gain_matches_sum_of_fund_pages(self, client, auth_token, app):
        with app.app_context():
            _, deployed_class = _make_class("Deployed Fund", "GAIN-B", "GAIN-B-I")
            _add_deployed_holding(deployed_class, "GAIN-B")
            db.session.add(NavHistory(share_class_id=deployed_class.id, nav_date=date.today(), nav_per_share=Decimal("110"), source="valuation"))
            # A second fund whose only batch isn't deployed yet.
            _, pending_class = _make_class("Pending Fund", "GAIN-C", "GAIN-C-I")
            _add_undeployed_deposit(pending_class, "GAIN-C", "7000.00")
            db.session.commit()

            data = client.get("/api/v1/stats/overview", headers=get_auth_headers(auth_token)).get_json()["data"]
            assert data["total_aum_usd"] == pytest.approx(11000.00)
            assert data["gain_usd"] == pytest.approx(1000.00)  # was 11,000 - 17,000 = -6,000
