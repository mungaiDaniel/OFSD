"""
Valuation Product Scoping (FUNDS vs SHARES) — Task 9
=====================================================
Funds and Shares valuations must never mix:
- GET /api/v1/valuation/funds?product=X and /api/v1/valuation/nav/runs?product=X
  are scoped by CoreFund.product_type (Task 8's chain down to ShareClass).
- POST /api/v1/valuation/preview and /api/v1/valuation/nav reject a request
  whose classes span both products, even without a product filter.

Run with: pytest tests/test_valuation_product_scoping.py -v
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.Funds.investor_shares import InvestorShares
from app.Valuation.valuation_snapshot import ValuationSnapshot


def get_auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_holding(fund_name, fund_code, class_code, currency):
    """Builds a full FUNDS or SHARES holding: CoreFund -> ShareClass -> Batch
    -> Investment -> InvestorShares, so a NAV valuation run can reconcile
    against it. product_type is omitted on CoreFund so the before_insert
    is_dangote_dprp_fund heuristic (Task 8) resolves it from fund_name/code,
    exactly like test_fund_product_split.py's own _make_fund_and_class —
    everything below inherits it via that same before_insert chain."""
    fund = CoreFund(fund_name=fund_name, fund_code=fund_code)
    db.session.add(fund)
    db.session.flush()

    share_class = ShareClass(
        core_fund_id=fund.id, class_name=f"{fund_name} Class", class_code=class_code, currency=currency
    )
    db.session.add(share_class)
    db.session.flush()

    batch = Batch(batch_name=f"{fund_code} Batch", share_class_id=share_class.id, stage=4, is_active=True)
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
        deployment_nav=Decimal("100.000000"),
        deployment_date=date.today() - timedelta(days=30),
    )
    db.session.add(holding)
    db.session.flush()

    return fund, share_class, holding


@pytest.fixture
def funds_holding(app):
    with app.app_context():
        fund, share_class, holding = _make_holding("Axiom", "AXIOM-PS", "AXIOM-PS-I", "USD")
        db.session.commit()
        return fund.id, share_class.id, holding.id


@pytest.fixture
def shares_holding(app):
    with app.app_context():
        fund, share_class, holding = _make_holding(
            "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP-PS", "DPRP-PS-I", "NGN"
        )
        db.session.commit()
        return fund.id, share_class.id, holding.id


@pytest.mark.unit
class TestValuationFundsListProductFilter:
    def test_product_funds_excludes_shares(self, client, auth_token, app, funds_holding, shares_holding):
        with app.app_context():
            resp = client.get("/api/v1/valuation/funds?product=FUNDS", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            names = [f["fund_name"] for f in resp.get_json()["data"]]
            assert "Axiom" in names
            assert "Dangote Petroleum Refinery and Petrochemicals FZE" not in names

    def test_product_shares_excludes_funds(self, client, auth_token, app, funds_holding, shares_holding):
        with app.app_context():
            resp = client.get("/api/v1/valuation/funds?product=SHARES", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            names = [f["fund_name"] for f in resp.get_json()["data"]]
            assert names == ["Dangote Petroleum Refinery and Petrochemicals FZE"]

    def test_no_product_filter_returns_both(self, client, auth_token, app, funds_holding, shares_holding):
        with app.app_context():
            resp = client.get("/api/v1/valuation/funds", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            names = {f["fund_name"] for f in resp.get_json()["data"]}
            assert {"Axiom", "Dangote Petroleum Refinery and Petrochemicals FZE"} <= names


@pytest.mark.unit
class TestNavRunsProductFilter:
    def _commit_snapshot(self, holding_id, nav_per_share, valuation_date):
        snap = ValuationSnapshot.create_snapshot(
            investor_shares_id=holding_id,
            valuation_date=valuation_date,
            nav_per_share=nav_per_share,
            shares_held=Decimal("100.000000"),
            deployment_nav=Decimal("100.000000"),
        )
        db.session.add(snap)
        db.session.commit()

    def test_runs_filtered_by_product(self, client, auth_token, app, funds_holding, shares_holding):
        _, _, funds_holding_id = funds_holding
        _, _, shares_holding_id = shares_holding
        with app.app_context():
            self._commit_snapshot(funds_holding_id, Decimal("105.00"), date.today())
            self._commit_snapshot(shares_holding_id, Decimal("110.00"), date.today())

            resp = client.get("/api/v1/valuation/nav/runs?product=FUNDS", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            fund_names = {r["fund_name"] for r in resp.get_json()["data"]}
            assert fund_names == {"Axiom"}

            resp = client.get("/api/v1/valuation/nav/runs?product=SHARES", headers=get_auth_headers(auth_token))
            assert resp.status_code == 200
            fund_names = {r["fund_name"] for r in resp.get_json()["data"]}
            assert fund_names == {"Dangote Petroleum Refinery and Petrochemicals FZE"}


@pytest.mark.unit
class TestCrossProductValuationRejected:
    """Task 9: 'NAV history, valuation snapshots and runs must be filtered by
    product so Funds and Shares valuations never mix' — defense in depth on
    the write path: a single preview/commit request may never span products."""

    def test_preview_rejects_mixed_products(self, client, auth_token, app, funds_holding, shares_holding):
        _, funds_class_id, _ = funds_holding
        _, shares_class_id, _ = shares_holding
        with app.app_context():
            payload = {
                "valuation_date": date.today().isoformat(),
                "classes": [
                    {"share_class_id": funds_class_id, "nav_per_share": "105.00", "total_fund_nav": "10500.00"},
                    {"share_class_id": shares_class_id, "nav_per_share": "110.00", "total_fund_nav": "11000.00"},
                ],
            }
            resp = client.post(
                "/api/v1/valuation/preview",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 400
            assert "Cannot mix FUNDS and SHARES" in resp.get_json()["message"]

    def test_preview_accepts_single_product(self, client, auth_token, app, funds_holding):
        _, funds_class_id, _ = funds_holding
        with app.app_context():
            payload = {
                "valuation_date": date.today().isoformat(),
                "classes": [
                    {"share_class_id": funds_class_id, "nav_per_share": "105.00", "total_fund_nav": "10500.00"},
                ],
            }
            resp = client.post(
                "/api/v1/valuation/preview",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 200

    def test_nav_commit_rejects_mixed_products(self, client, auth_token, app, funds_holding, shares_holding):
        _, funds_class_id, _ = funds_holding
        _, shares_class_id, _ = shares_holding
        with app.app_context():
            payload = {
                "valuation_date": date.today().isoformat(),
                "classes": [
                    {"share_class_id": funds_class_id, "nav_per_share": "105.00", "total_fund_nav": "10500.00"},
                    {"share_class_id": shares_class_id, "nav_per_share": "110.00", "total_fund_nav": "11000.00"},
                ],
            }
            resp = client.post(
                "/api/v1/valuation/nav",
                data=json.dumps(payload),
                headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
            )
            assert resp.status_code == 400
            assert "Cannot mix FUNDS and SHARES" in resp.get_json()["message"]
