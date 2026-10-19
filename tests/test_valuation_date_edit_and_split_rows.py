"""
Valuation date edit (super_admin only) and the separate Deposit / Deployment
statement rows.

Run with: pytest tests/test_valuation_date_edit_and_split_rows.py -v
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.investor_shares import InvestorShares
from app.Funds.nav_history import NavHistory
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment
from app.Investments.route import get_investor_statements
from app.Valuation.valuation_snapshot import ValuationSnapshot


def _utc(d):
    return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)


def _seed(deposited, deployed, valuation_dates):
    fund = CoreFund(fund_name="Edit Fund", fund_code="EDIT")
    db.session.add(fund)
    db.session.flush()
    sc = ShareClass(core_fund_id=fund.id, class_name="Edit Class", class_code="EDIT-I", currency="USD")
    db.session.add(sc)
    db.session.flush()
    batch = Batch(
        batch_name="Edit Batch", share_class_id=sc.id, stage=4, is_active=True, deployment_confirmed=True,
        date_deployed=_utc(deployed), deployment_date_actual=deployed, deployment_nav=Decimal("41.12"),
    )
    db.session.add(batch)
    db.session.flush()
    inv = Investment(
        investor_name="Edit Investor", investor_email="edit@example.com", internal_client_code="EDIT-1",
        amount_deposited=Decimal("2433.23"), batch_id=batch.id, fund_id=fund.id,
        fund_name=fund.fund_name, share_class_id=sc.id, date_deposited=_utc(deposited),
    )
    db.session.add(inv)
    db.session.flush()
    holding = InvestorShares(
        investment_id=inv.id, share_class_id=sc.id, batch_id=batch.id,
        shares_owned=Decimal("59.1739"), deployment_nav=Decimal("41.12"), deployment_date=deployed,
    )
    db.session.add(holding)
    db.session.flush()
    db.session.add(NavHistory(share_class_id=sc.id, nav_date=deployed, nav_per_share=Decimal("41.12"), source="deployment"))
    for vd in valuation_dates:
        db.session.add(ValuationSnapshot(
            investor_shares_id=holding.id, valuation_date=vd, nav_per_share=Decimal("38.37"),
            shares_held=Decimal("59.1739"), market_value=Decimal("2270.50"), performance_pct=Decimal("-6.69"),
        ))
        db.session.add(NavHistory(share_class_id=sc.id, nav_date=vd, nav_per_share=Decimal("38.37"), source="valuation"))
    db.session.commit()
    return sc.id


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _statements():
    res = get_investor_statements.__wrapped__("EDIT-1")
    return res.get_json()["data"]


@pytest.mark.unit
class TestSplitDepositAndDeploymentRows:
    def test_different_days_give_two_rows(self, app):
        with app.app_context():
            _seed(date(2026, 8, 13), date(2026, 8, 20), [])
            rows = sorted((r for r in _statements() if r["type"] in ("DEPOSIT", "DEPLOYMENT")), key=lambda r: r["date"])
            assert [r["type"] for r in rows] == ["DEPOSIT", "DEPLOYMENT"]
            deposit, deployment = rows
            assert deposit["date"].startswith("2026-08-13") and deployment["date"].startswith("2026-08-20")
            assert deposit["deposits"] == 2433.23 and deployment["deposits"] == 0.0
            # Shares/NAV exist only once deployed; balance is carried, not doubled.
            assert deposit["shares"] is None and deployment["shares"] is not None
            assert deployment["end_balance"] == 2433.23

    def test_same_day_stays_one_row(self, app):
        with app.app_context():
            _seed(date(2026, 8, 13), date(2026, 8, 13), [])
            rows = [r for r in _statements() if r["type"] in ("DEPOSIT", "DEPLOYMENT")]
            assert len(rows) == 1


@pytest.mark.unit
class TestEditValuationDate:
    def _put(self, client, token, sc_id, old, new):
        return client.put(
            "/api/v1/valuation/nav/runs/date",
            data=json.dumps({"share_class_id": sc_id, "old_date": old, "new_date": new}),
            headers=_headers(token),
        )

    def test_admin_forbidden(self, client, app, admin_auth_token):
        with app.app_context():
            sc_id = _seed(date(2026, 8, 13), date(2026, 8, 13), [date(2026, 10, 16)])
        assert self._put(client, admin_auth_token, sc_id, "2026-10-16", "2026-10-15").status_code == 403

    def test_date_moves_everywhere(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id = _seed(date(2026, 8, 13), date(2026, 8, 13), [date(2026, 10, 16)])
        r = self._put(client, super_admin_auth_token, sc_id, "2026-10-16", "2026-10-15")
        assert r.status_code == 200, r.get_data(as_text=True)
        with app.app_context():
            vals = [x for x in _statements() if x["type"] == "VALUATION"]
            assert [x["date"] for x in vals] == ["2026-10-15"]
            assert db.session.query(NavHistory).filter_by(share_class_id=sc_id, source="valuation", nav_date=date(2026, 10, 15)).count() == 1
            assert db.session.query(NavHistory).filter_by(share_class_id=sc_id, source="valuation", nav_date=date(2026, 10, 16)).count() == 0

    def test_must_stay_between_neighbouring_valuations(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id = _seed(date(2026, 8, 13), date(2026, 8, 13), [date(2026, 9, 10), date(2026, 10, 16)])
        assert self._put(client, super_admin_auth_token, sc_id, "2026-10-16", "2026-09-05").status_code == 400
        assert self._put(client, super_admin_auth_token, sc_id, "2026-10-16", "2026-09-10").status_code == 409

    def test_cannot_precede_deployment(self, client, app, super_admin_auth_token):
        with app.app_context():
            sc_id = _seed(date(2026, 8, 13), date(2026, 8, 13), [date(2026, 10, 16)])
        assert self._put(client, super_admin_auth_token, sc_id, "2026-10-16", "2026-08-01").status_code == 400


@pytest.mark.unit
def test_batch_list_returns_aggregated_figures(client, app, super_admin_auth_token):
    with app.app_context():
        _seed(date(2026, 8, 13), date(2026, 8, 20), [])
    r = client.get("/api/v1/batches", headers=_headers(super_admin_auth_token))
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = r.get_json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["total_principal"] == 2433.23 and row["investors_count"] == 1
    assert row["funds"] == [{"fund_name": "Edit Fund", "total_principal": 2433.23, "investors_count": 1}]
    assert row["class_code"] == "EDIT-I"
