"""
Edit fund / share and share class — Task 12
============================================
Covers app/Funds/edit_service.py through the real HTTP endpoints, on BOTH
products (/api/v1/funds/... and /api/v1/shares/...):

* name / description / status edits succeed and are audit-logged
* unique name / code validation, product immutability, cross-product 404
* share class currency: free on an empty class, 409 once deposits exist,
  super_admin override only with confirm_currency_override (+ audit entry)
* deactivation blocked by open batches
* optimistic concurrency (stale version -> 409)
* role check (non super_admin -> 403)

Run with: pytest tests/test_fund_edit.py -v
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.database.database import db
from app.database.product_type import FUNDS, SHARES
from app.Admin.model import User
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment
from app.utils.audit_log import AuditLog


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_user(role, email):
    user = User(name=f"{role} user", email=email, role=role, status="active")
    user.password = User.generate_password_hash("Test1234!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def super_admin_token(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        _make_user("super_admin", "edit_super@example.com")
        # Real login tokens use the EMAIL as identity — exercise that path.
        return create_access_token(identity="edit_super@example.com", additional_claims={"admin": 2})


@pytest.fixture
def admin_token(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        _make_user("admin", "edit_admin@example.com")
        return create_access_token(identity="edit_admin@example.com", additional_claims={"admin": 1})


def _seed(product):
    """One fund/share with one share class. Returns (fund_id, class_id)."""
    if product == SHARES:
        fund = CoreFund(fund_name="Dangote Petroleum Refinery and Petrochemicals FZE", fund_code="DPRP",
                        product_type=SHARES)
        currency, code = "NGN", "DPRP-NGN"
    else:
        fund = CoreFund(fund_name="Axiom", fund_code="AXM", product_type=FUNDS)
        currency, code = "USD", "AXM-USD"
    db.session.add(fund)
    db.session.flush()
    sc = ShareClass(core_fund_id=fund.id, class_name="Class I", class_code=code, currency=currency)
    db.session.add(sc)
    db.session.commit()
    return fund.id, sc.id


def _add_deposit(fund_id, class_id, batch_name="Batch A", is_open=False):
    batch = Batch(batch_name=batch_name, certificate_number=f"CERT-{batch_name}",
                  total_principal=Decimal("1000.00"), share_class_id=class_id, is_open=is_open)
    db.session.add(batch)
    db.session.flush()
    inv = Investment(batch_id=batch.id, investor_name="Test Investor", investor_email="t@example.com",
                     internal_client_code=f"C-{batch.id}", amount_deposited=Decimal("1000.00"),
                     date_deposited=datetime.now(timezone.utc), fund_id=fund_id, share_class_id=class_id,
                     fund_name=db.session.get(CoreFund, fund_id).fund_name)
    db.session.add(inv)
    db.session.commit()
    return batch.id


def _ctx(client, token, base, fund_id):
    r = client.get(f"/api/v1/{base}/{fund_id}/edit-context", headers=_headers(token))
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


PRODUCTS = [(FUNDS, "funds"), (SHARES, "shares")]


@pytest.mark.unit
@pytest.mark.parametrize("product,base", PRODUCTS)
class TestEditFund:

    def test_edit_name_description_status_is_audited(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, _ = _seed(product)
        ctx = _ctx(client, super_admin_token, base, fund_id)
        new_name = "Axiom Global" if product == FUNDS else "Dangote Petroleum Refinery FZE"
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token), data=json.dumps({
            "fund_name": new_name, "description": "Edited description", "is_active": False,
            "version": ctx["fund"]["version"],
        }))
        assert r.status_code == 200, r.get_json()
        body = r.get_json()["data"]
        assert body["fund_name"] == new_name  # NOT title-cased
        assert body["description"] == "Edited description"
        assert body["is_active"] is False
        assert body["product_type"] == product
        with app.app_context():
            log = AuditLog.query.filter_by(target_id=fund_id).filter(
                AuditLog.action.in_(("UPDATE_FUND", "UPDATE_SHARE"))).one()
            old, new = json.loads(log.old_value), json.loads(log.new_value)
            assert new["fund_name"] == new_name and new["is_active"] is False
            assert "fund_name" in old and old["is_active"] is True
            assert log.user_email == "edit_super@example.com"
            assert log.ip_address

    def test_rename_cascades_to_deposits(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
            _add_deposit(fund_id, class_id)
        new_name = "Axiom Renamed" if product == FUNDS else "Dangote DPRP Renamed"
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"fund_name": new_name}))
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert {i.fund_name for i in Investment.query.filter_by(fund_id=fund_id)} == {new_name}

    def test_duplicate_code_within_product_rejected(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, _ = _seed(product)
            other = CoreFund(fund_name="Other Thing" if product == FUNDS else "Dangote Other",
                             fund_code="OTH", product_type=product)
            db.session.add(other)
            db.session.commit()
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"fund_code": "oth"}))
        assert r.status_code == 409
        assert "fund_code" in r.get_json()["errors"]

    def test_empty_name_rejected_inline(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, _ = _seed(product)
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"fund_name": "   "}))
        assert r.status_code == 400
        assert "fund_name" in r.get_json()["errors"]

    def test_product_cannot_be_changed(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, _ = _seed(product)
        other = SHARES if product == FUNDS else FUNDS
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"product_type": other}))
        assert r.status_code == 400
        assert r.get_json()["code"] == "PRODUCT_IMMUTABLE"
        with app.app_context():
            assert db.session.get(CoreFund, fund_id).product_type == product

    def test_cross_product_edit_404s(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
        wrong = "shares" if base == "funds" else "funds"
        r = client.patch(f"/api/v1/{wrong}/{fund_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"fund_name": "Hijack"}))
        assert r.status_code == 404
        r = client.patch(f"/api/v1/{wrong}/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"class_name": "Hijack"}))
        assert r.status_code == 404
        r = client.get(f"/api/v1/{wrong}/{fund_id}/edit-context", headers=_headers(super_admin_token))
        assert r.status_code == 404

    def test_stale_version_conflicts(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, _ = _seed(product)
        version = _ctx(client, super_admin_token, base, fund_id)["fund"]["version"]
        r1 = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                          data=json.dumps({"description": "first", "version": version}))
        assert r1.status_code == 200
        r2 = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                          data=json.dumps({"description": "second", "version": version}))
        assert r2.status_code == 409
        assert r2.get_json()["code"] == "VERSION_CONFLICT"

    def test_deactivate_blocked_by_open_batch(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
            _add_deposit(fund_id, class_id, batch_name="Open Batch 1", is_open=True)
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"is_active": False}))
        assert r.status_code == 409
        body = r.get_json()
        assert body["code"] == "DEACTIVATION_BLOCKED"
        assert "Open Batch 1" in body["blockers"]

    def test_non_super_admin_forbidden(self, client, app, admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
        r = client.patch(f"/api/v1/{base}/{fund_id}", headers=_headers(admin_token),
                         data=json.dumps({"fund_name": "Nope"}))
        assert r.status_code == 403
        r = client.patch(f"/api/v1/{base}/{fund_id}/classes/{class_id}", headers=_headers(admin_token),
                         data=json.dumps({"class_name": "Nope"}))
        assert r.status_code == 403


@pytest.mark.unit
@pytest.mark.parametrize("product,base", PRODUCTS)
class TestEditShareClass:

    def test_edit_name_code_status_is_audited(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
        ctx = _ctx(client, super_admin_token, base, fund_id)
        version = ctx["share_classes"][0]["version"]
        r = client.patch(f"/api/v1/{base}/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"class_name": "Class A", "class_code": "new-a",
                                          "is_active": False, "version": version}))
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert data["class_code"] == "NEW-A" and data["is_active"] is False
        with app.app_context():
            assert AuditLog.query.filter_by(action="UPDATE_SHARE_CLASS", target_id=class_id).count() == 1

    def test_product_cannot_be_changed(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
        other = SHARES if product == FUNDS else FUNDS
        r = client.patch(f"/api/v1/{base}/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"product_type": other}))
        assert r.status_code == 400

    def test_currency_outside_product_allow_list_rejected(self, client, app, super_admin_token, product, base):
        with app.app_context():
            fund_id, class_id = _seed(product)
        # SHARES allows every DB-legal currency (USD/NGN/KES), so use one the
        # app doesn't support at all.
        bad = "NGN" if product == FUNDS else "EUR"
        r = client.patch(f"/api/v1/{base}/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"currency": bad}))
        assert r.status_code == 400
        assert "currency" in r.get_json()["errors"]


@pytest.mark.unit
class TestShareClassCurrencyLock:
    """The change/lock/override flow is exercised on FUNDS (KES/USD); SHARES
    shares the same code path with USD/NGN/KES allowed."""

    @pytest.mark.parametrize("currency", ["USD", "NGN", "KES"])
    def test_shares_class_accepts_usd_ngn_kes(self, client, app, super_admin_token, currency):
        with app.app_context():
            fund_id, class_id = _seed(SHARES)
        ctx = _ctx(client, super_admin_token, "shares", fund_id)
        assert ctx["allowed_currencies"] == ["USD", "NGN", "KES"]
        r = client.patch(f"/api/v1/shares/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"currency": currency}))
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["currency"] == currency

    def test_currency_change_allowed_on_empty_class(self, client, app, super_admin_token):
        with app.app_context():
            fund_id, class_id = _seed(FUNDS)
        ctx = _ctx(client, super_admin_token, "funds", fund_id)
        assert ctx["share_classes"][0]["currency_locked"] is False
        r = client.patch(f"/api/v1/funds/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"currency": "KES"}))
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["currency"] == "KES"

    def test_currency_change_blocked_once_deposits_exist(self, client, app, super_admin_token):
        with app.app_context():
            fund_id, class_id = _seed(FUNDS)
            _add_deposit(fund_id, class_id)
        ctx = _ctx(client, super_admin_token, "funds", fund_id)
        sc = ctx["share_classes"][0]
        assert sc["currency_locked"] is True and sc["currency_lock_reasons"]
        r = client.patch(f"/api/v1/funds/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"currency": "KES", "version": sc["version"]}))
        assert r.status_code == 409
        body = r.get_json()
        assert body["code"] == "CURRENCY_LOCKED"
        assert body["can_override"] is True
        with app.app_context():
            assert db.session.get(ShareClass, class_id).currency == "USD"
            assert AuditLog.query.filter_by(target_id=class_id).count() == 0

    def test_super_admin_override_changes_currency_and_is_audited(self, client, app, super_admin_token):
        with app.app_context():
            fund_id, class_id = _seed(FUNDS)
            _add_deposit(fund_id, class_id)
        sc = _ctx(client, super_admin_token, "funds", fund_id)["share_classes"][0]
        r = client.patch(f"/api/v1/funds/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"currency": "KES", "version": sc["version"],
                                          "confirm_currency_override": True}))
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert db.session.get(ShareClass, class_id).currency == "KES"
            inv = Investment.query.filter_by(share_class_id=class_id).one()
            assert inv.amount_deposited == Decimal("1000.00")  # figures NOT converted
            override = AuditLog.query.filter_by(action="SHARE_CLASS_CURRENCY_OVERRIDE", target_id=class_id).one()
            assert "NOT converted" in override.description
            assert json.loads(override.old_value) == {"currency": "USD"}
            assert json.loads(override.new_value) == {"currency": "KES"}

    def test_override_flag_must_be_explicit_true(self, client, app, super_admin_token):
        with app.app_context():
            fund_id, class_id = _seed(FUNDS)
            _add_deposit(fund_id, class_id)
        r = client.patch(f"/api/v1/funds/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"currency": "KES", "confirm_currency_override": "yes"}))
        assert r.status_code == 409

    def test_deactivate_class_blocked_by_open_batch(self, client, app, super_admin_token):
        with app.app_context():
            fund_id, class_id = _seed(FUNDS)
            _add_deposit(fund_id, class_id, batch_name="Open Class Batch", is_open=True)
        r = client.patch(f"/api/v1/funds/{fund_id}/classes/{class_id}", headers=_headers(super_admin_token),
                         data=json.dumps({"is_active": False}))
        assert r.status_code == 409
        assert "Open Class Batch" in r.get_json()["blockers"]
