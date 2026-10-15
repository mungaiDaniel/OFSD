"""
Manual per-investor Deployment NAVs (FUNDS) — "list all clients, enter NAV"
feature, mirroring the manual Transfer amounts feature.
=============================================================================
Each investor can be deployed at their own NAV per share instead of one NAV
for their whole share class. The single-NAV-per-class mode (deployment_breakdown
only, no deployment_navs) must keep working unchanged.

Run with: pytest tests/test_deploy_manual_navs.py -v
"""

import json
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Batch.model import Batch
from app.Investments.model import Investment


def get_auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_transferred_batch(amounts):
    fund = CoreFund(fund_name="Axiom Deploy Test", fund_code="AXM-DEPL")
    db.session.add(fund)
    db.session.flush()
    share_class = ShareClass(core_fund_id=fund.id, class_name="Axiom Class", class_code="AXM-DEPL-I", currency="USD")
    db.session.add(share_class)
    db.session.flush()
    batch = Batch(batch_name="Axiom Deploy Batch", share_class_id=share_class.id, stage=2, is_active=True, is_transferred=True)
    db.session.add(batch)
    db.session.flush()

    investments = []
    for i, amount in enumerate(amounts, start=1):
        inv = Investment(
            investor_name=f"Investor {i}",
            investor_email=f"investor{i}@example.com",
            internal_client_code=f"DEPL-{i}",
            amount_deposited=Decimal(str(amount)),
            batch_id=batch.id,
            fund_id=fund.id,
            share_class_id=share_class.id,
        )
        db.session.add(inv)
        investments.append(inv)
    db.session.commit()
    for inv in investments:
        db.session.refresh(inv)
    return batch, share_class, investments


def _deploy_payload(share_class, nav, total_shares, total_nav, deployment_navs=None):
    payload = {
        "stage": 3,
        "deployment_confirmed": True,
        "date_deployed": "2026-10-01T00:00:00Z",
        "deployment_nav": nav,
        "total_shares": total_shares,
        "total_nav": total_nav,
        "deployment_breakdown": [{
            "share_class_id": share_class.id,
            "class_code": share_class.class_code,
            "navPerShare": nav,
            "totalShares": total_shares,
            "totalNav": total_nav,
        }],
    }
    if deployment_navs is not None:
        payload["deployment_navs"] = deployment_navs
    return payload


@pytest.mark.unit
class TestManualDeploymentNavs:
    def test_each_investor_deployed_at_their_own_nav(self, client, auth_token, app):
        with app.app_context():
            batch, share_class, (inv_a, inv_b) = _make_transferred_batch(["1000.00", "3000.00"])

            # A at NAV 100 -> 10 shares; B at NAV 120 -> 25 shares.
            payload = _deploy_payload(
                share_class, nav=114.2857, total_shares=35, total_nav=4000,
                deployment_navs={str(inv_a.id): 100, str(inv_b.id): 120},
            )
            resp = client.patch(f"/api/v1/batches/{batch.id}", data=json.dumps(payload), headers=get_auth_headers(auth_token))
            assert resp.status_code == 200

            a = db.session.get(Investment, inv_a.id)
            b = db.session.get(Investment, inv_b.id)
            assert a.shares_owned == Decimal("10.0000")
            assert Decimal(str(a.previous_nav_price)) == Decimal("100")
            assert b.shares_owned == Decimal("25.0000")
            assert Decimal(str(b.previous_nav_price)) == Decimal("120")

            refreshed = db.session.get(Batch, batch.id)
            assert refreshed.total_shares == Decimal("35.0000")
            assert refreshed.deployment_total_nav == Decimal("4000.00")

    def test_investor_missing_from_map_falls_back_to_class_nav(self, client, auth_token, app):
        with app.app_context():
            batch, share_class, (inv_a, inv_b) = _make_transferred_batch(["1000.00", "2000.00"])

            payload = _deploy_payload(
                share_class, nav=200, total_shares=15, total_nav=3000,
                deployment_navs={str(inv_a.id): 100},
            )
            resp = client.patch(f"/api/v1/batches/{batch.id}", data=json.dumps(payload), headers=get_auth_headers(auth_token))
            assert resp.status_code == 200

            assert db.session.get(Investment, inv_a.id).shares_owned == Decimal("10.0000")
            assert db.session.get(Investment, inv_b.id).shares_owned == Decimal("10.0000")  # 2000 / class NAV 200

    def test_non_positive_nav_rejected(self, client, auth_token, app):
        with app.app_context():
            batch, share_class, (inv_a,) = _make_transferred_batch(["1000.00"])
            payload = _deploy_payload(share_class, nav=100, total_shares=10, total_nav=1000, deployment_navs={str(inv_a.id): 0})
            resp = client.patch(f"/api/v1/batches/{batch.id}", data=json.dumps(payload), headers=get_auth_headers(auth_token))
            assert resp.status_code == 400
            assert db.session.get(Batch, batch.id).deployment_confirmed in (False, None)

    def test_single_class_nav_mode_unchanged(self, client, auth_token, app):
        with app.app_context():
            batch, share_class, (inv_a, inv_b) = _make_transferred_batch(["1000.00", "3000.00"])
            payload = _deploy_payload(share_class, nav=100, total_shares=40, total_nav=4000)
            resp = client.patch(f"/api/v1/batches/{batch.id}", data=json.dumps(payload), headers=get_auth_headers(auth_token))
            assert resp.status_code == 200

            assert db.session.get(Investment, inv_a.id).shares_owned == Decimal("10.0000")
            assert db.session.get(Investment, inv_b.id).shares_owned == Decimal("30.0000")

    def test_each_investor_gets_their_own_deployment_date(self, client, auth_token, app):
        from datetime import date
        from app.Funds.investor_shares import InvestorShares

        with app.app_context():
            batch, share_class, (inv_a, inv_b) = _make_transferred_batch(["1000.00", "3000.00"])

            payload = _deploy_payload(
                share_class, nav=114.2857, total_shares=35, total_nav=4000,
                deployment_navs={str(inv_a.id): 100, str(inv_b.id): 120},
            )
            payload["deployment_dates"] = {str(inv_a.id): "2026-10-01", str(inv_b.id): "2026-10-08"}
            resp = client.patch(f"/api/v1/batches/{batch.id}", data=json.dumps(payload), headers=get_auth_headers(auth_token))
            assert resp.status_code == 200

            assert db.session.get(Investment, inv_a.id).date_transferred.date() == date(2026, 10, 1)
            assert db.session.get(Investment, inv_b.id).date_transferred.date() == date(2026, 10, 8)
            shares_b = db.session.query(InvestorShares).filter(InvestorShares.investment_id == inv_b.id).one()
            assert shares_b.deployment_date == date(2026, 10, 8)

    def test_invalid_deployment_date_rejected(self, client, auth_token, app):
        with app.app_context():
            batch, share_class, (inv_a,) = _make_transferred_batch(["1000.00"])
            payload = _deploy_payload(share_class, nav=100, total_shares=10, total_nav=1000, deployment_navs={str(inv_a.id): 100})
            payload["deployment_dates"] = {str(inv_a.id): "not-a-date"}
            resp = client.patch(f"/api/v1/batches/{batch.id}", data=json.dumps(payload), headers=get_auth_headers(auth_token))
            assert resp.status_code == 400
