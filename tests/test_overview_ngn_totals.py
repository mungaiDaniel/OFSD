"""
Overview NGN totals + "Not valued yet" flag — Task 10
=======================================================
GET /api/v1/stats/overview must expose a SHARES-scoped NGN total/gain
(total_ngn, gain_ngn) alongside the existing FUNDS-scoped KES/USD figures,
without ever mixing the two products together. compute_funds_summary_data's
per-class "is_valued" flag must distinguish a real committed valuation from
the deployment-NAV fallback price, so the Overview NGN card can show
"Not valued yet" instead of a fabricated Gain/Loss.

Run with: pytest tests/test_overview_ngn_totals.py -v
"""

import json
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


def _make_holding(fund_name, fund_code, class_code, currency, deployment_nav="100.000000"):
    fund = CoreFund(fund_name=fund_name, fund_code=fund_code)
    db.session.add(fund)
    db.session.flush()

    share_class = ShareClass(
        core_fund_id=fund.id, class_name=f"{fund_name} Class", class_code=class_code, currency=currency
    )
    db.session.add(share_class)
    db.session.flush()

    batch = Batch(
        batch_name=f"{fund_code} Batch",
        share_class_id=share_class.id,
        stage=4,
        is_active=True,
        date_deployed=datetime.now(timezone.utc) - timedelta(days=30),
        deployment_nav=Decimal(deployment_nav),
    )
    db.session.add(batch)
    db.session.flush()

    investment = Investment(
        investor_name="Test Investor",
        investor_email="investor@example.com",
        internal_client_code=f"{fund_code}-001",
        amount_deposited=Decimal("10000.00"),
        batch_id=batch.id,
        share_class_id=share_class.id,
    )
    db.session.add(investment)
    db.session.flush()

    holding = InvestorShares(
        investment_id=investment.id,
        share_class_id=share_class.id,
        batch_id=batch.id,
        shares_owned=Decimal("100.000000"),
        deployment_nav=Decimal(deployment_nav),
        deployment_date=date.today() - timedelta(days=30),
    )
    db.session.add(holding)
    db.session.flush()

    return fund, share_class, batch, holding


@pytest.mark.unit
class TestOverviewNgnTotals:
    def test_overview_stats_exposes_ngn_total_scoped_to_shares(self, client, auth_token, app):
        with app.app_context():
            # A FUNDS (KES) holding and a SHARES (NGN) holding — the NGN total
            # must reflect only the SHARES side, never summed with KES/USD.
            _make_holding("Axiom", "AXIOM-OV", "AXIOM-OV-I", "KES", deployment_nav="100.000000")
            _, shares_class, _, _ = _make_holding(
                "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP-OV", "DPRP-OV-I", "NGN",
                deployment_nav="500.000000",
            )
            # Commit a real valuation above deployment NAV so there's a
            # non-zero, unambiguous gain to assert on.
            db.session.add(NavHistory(
                share_class_id=shares_class.id, nav_date=date.today(),
                nav_per_share=Decimal("550.000000"), source="valuation",
            ))
            db.session.commit()

            resp = client.get("/api/v1/stats/overview", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            data = resp.get_json()["data"]

            assert "total_ngn" in data and "gain_ngn" in data
            # 100 shares * 550 NAV = 55,000 total. Overview's Gain/Loss is
            # current value vs. Net Holdings (gross deposited here, since this
            # fixture has no fees/withdrawals) = 10,000 -> gain 45,000.
            assert data["total_ngn"] == pytest.approx(55000.00)
            assert data["gain_ngn"] == pytest.approx(45000.00)
            # NGN must never be folded into the KES/USD figures.
            assert data["total_aum_kes"] != data["total_ngn"]

    def test_overview_stats_ngn_zero_when_no_shares_holdings(self, client, auth_token, app):
        with app.app_context():
            _make_holding("Axiom", "AXIOM-OV2", "AXIOM-OV2-I", "KES")

            resp = client.get("/api/v1/stats/overview", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            data = resp.get_json()["data"]
            assert data.get("total_ngn") == 0.0


@pytest.mark.unit
class TestShareClassIsValuedFlag:
    """FundClassSummary.is_valued (Task 10): true only once a real valuation
    has been committed, not merely because the position was deployed."""

    def test_is_valued_false_before_any_valuation_committed(self, client, app):
        with app.app_context():
            _make_holding(
                "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP-NV", "DPRP-NV-I", "NGN",
                deployment_nav="500.000000",
            )
            db.session.commit()

            resp = client.get("/api/v1/shares/summary")
            assert resp.status_code == 200
            classes = resp.get_json()["data"]["funds"][0]["classes"]
            assert classes[0]["is_valued"] is False
            # Still has a price (the deployment-NAV fallback) even though unvalued.
            assert classes[0]["current_nav"] == pytest.approx(500.0)

    def test_is_valued_true_after_valuation_committed(self, client, app):
        with app.app_context():
            _, shares_class, _, _ = _make_holding(
                "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP-V", "DPRP-V-I", "NGN",
                deployment_nav="500.000000",
            )
            db.session.add(NavHistory(
                share_class_id=shares_class.id, nav_date=date.today(),
                nav_per_share=Decimal("525.000000"), source="valuation",
            ))
            db.session.commit()

            resp = client.get("/api/v1/shares/summary")
            assert resp.status_code == 200
            classes = resp.get_json()["data"]["funds"][0]["classes"]
            assert classes[0]["is_valued"] is True
            assert classes[0]["current_nav"] == pytest.approx(525.0)
