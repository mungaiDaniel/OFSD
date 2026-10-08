"""
Fund-Level Product Split (FUNDS vs SHARES) — Task 8
=====================================================
Moves the FUNDS/SHARES classification up to the fund level:
CoreFund.product_type is now the authoritative source of truth (instead of
batches/investments each independently guessing it from fund name/code via
is_dangote_dprp_fund — Task 1). ShareClass/Batch/Investment each inherit and
validate their product_type against the row above them in that chain.

Covers: migration 020's backfill preserves row counts and correctly tags
DPRP as SHARES; /api/v1/funds excludes DPRP; /api/v1/shares returns only
DPRP and its classes; cross-product references are rejected at every layer
(share class under the wrong fund, batch under the wrong share class,
reaching a fund_id through the wrong product's URL).

Run with: pytest tests/test_fund_product_split.py -v
"""

import importlib.util
import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database.database import db
from app.database.product_type import FUNDS, SHARES
from app.Admin.model import User
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment
from app.logic.batch_management_service import BatchManagementService


def get_auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


def _load_migration_020():
    """Load migrations/versions/020_add_fund_product_type.py by path — its
    filename starts with a digit, so it isn't importable as a normal dotted
    module (same trick tests/test_product_type.py uses for migration 017)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "migrations", "versions", "020_add_fund_product_type.py")
    spec = importlib.util.spec_from_file_location("migration_020_add_fund_product_type", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_fund_and_class(fund_name, fund_code, class_code="CI-USD", currency="USD"):
    """Mirrors tests/test_product_type.py's helper — omits product_type so the
    CoreFund.before_insert heuristic fallback (Task 8) resolves it, exactly
    like every pre-Task-8 call site in the app still does."""
    fund = CoreFund(fund_name=fund_name, fund_code=fund_code)
    db.session.add(fund)
    db.session.flush()
    share_class = ShareClass(
        core_fund_id=fund.id,
        class_name=f"{fund_name} Class",
        class_code=class_code,
        currency=currency,
    )
    db.session.add(share_class)
    db.session.flush()
    return fund, share_class


@pytest.fixture
def super_admin_token(app):
    """A real super_admin User + a token whose identity resolves to it —
    app/Funds/routes.py's _require_super_admin() checks User.id against the
    JWT identity, unlike the plain 'admin' claim the shared conftest
    auth_token fixture uses elsewhere."""
    from flask_jwt_extended import create_access_token

    with app.app_context():
        user = User(name="Super Admin", email="super_admin@example.com", role="super_admin", status="active")
        user.password = User.generate_password_hash("Test1234!")
        db.session.add(user)
        db.session.commit()
        return create_access_token(identity=str(user.id), additional_claims={"admin": 2})


@pytest.mark.unit
class TestMigration020Backfill:
    """Exercises the real migration 020 backfill SQL against seed-like data."""

    def test_backfill_preserves_counts_and_tags_dprp_as_shares(self, app):
        with app.app_context():
            db.create_all()
            try:
                funds_fund, _ = _make_fund_and_class("Axiom", "AXIOM")
                shares_fund, _ = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP", currency="USD"
                )

                before_fund_count = CoreFund.query.count()
                before_class_count = ShareClass.query.count()

                conn = db.session.connection()
                # Simulate the moment right after `ADD COLUMN product_type` in the
                # real migration, before its backfill UPDATEs run.
                conn.execute(text("ALTER TABLE core_funds ALTER COLUMN product_type DROP NOT NULL"))
                conn.execute(text("ALTER TABLE share_classes ALTER COLUMN product_type DROP NOT NULL"))
                conn.execute(text("UPDATE core_funds SET product_type = NULL"))
                conn.execute(text("UPDATE share_classes SET product_type = NULL"))

                migration = _load_migration_020()
                migration._backfill_fund_product_type(conn)

                conn.execute(text("ALTER TABLE core_funds ALTER COLUMN product_type SET NOT NULL"))
                conn.execute(text("ALTER TABLE share_classes ALTER COLUMN product_type SET NOT NULL"))

                db.session.commit()
                db.session.expire_all()

                assert CoreFund.query.count() == before_fund_count
                assert ShareClass.query.count() == before_class_count

                assert db.session.get(CoreFund, funds_fund.id).product_type == FUNDS
                assert db.session.get(CoreFund, shares_fund.id).product_type == SHARES

                classes_by_fund_id = {sc.core_fund_id: sc.product_type for sc in ShareClass.query.all()}
                assert classes_by_fund_id[funds_fund.id] == FUNDS
                assert classes_by_fund_id[shares_fund.id] == SHARES
            finally:
                db.session.remove()
                db.drop_all()

    def test_backfill_count_summary_matches_before_and_after(self, app):
        """_print_fund_product_type_counts totals add up to the same row counts before/after."""
        with app.app_context():
            db.create_all()
            try:
                _make_fund_and_class("Atium", "ATIUM")
                _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-2", currency="USD"
                )

                conn = db.session.connection()
                migration = _load_migration_020()
                counts = migration._print_fund_product_type_counts(conn, "unit test")

                assert sum(counts["core_funds"].values()) == CoreFund.query.count()
                assert sum(counts["share_classes"].values()) == ShareClass.query.count()
            finally:
                db.session.remove()
                db.drop_all()


@pytest.mark.unit
class TestProductScopedFundEndpoints:
    """GET /api/v1/funds vs GET /api/v1/shares — same code, different product."""

    def test_funds_list_excludes_dprp(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _make_fund_and_class("Axiom", "AXIOM")
                _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-3", currency="USD"
                )

                resp = client.get("/api/v1/funds", headers=get_auth_headers(auth_token))
                assert resp.status_code == 200
                names = [f["fund_name"] for f in resp.get_json()["data"]]
                assert "Axiom" in names
                assert "Dangote Petroleum Refinery and Petrochemicals FZE" not in names
            finally:
                db.session.remove()
                db.drop_all()

    def test_shares_list_returns_only_dprp(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _make_fund_and_class("Axiom", "AXIOM")
                _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-4", currency="USD"
                )

                resp = client.get("/api/v1/shares", headers=get_auth_headers(auth_token))
                assert resp.status_code == 200
                names = [f["fund_name"] for f in resp.get_json()["data"]]
                assert names == ["Dangote Petroleum Refinery and Petrochemicals FZE"]
            finally:
                db.session.remove()
                db.drop_all()

    def test_shares_detail_returns_dprp_classes(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                dprp_fund, dprp_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-5", currency="USD"
                )
                fund_id = dprp_fund.id

                resp = client.get(f"/api/v1/shares/{fund_id}", headers=get_auth_headers(auth_token))
                assert resp.status_code == 200
                data = resp.get_json()["data"]
                assert data["product_type"] == SHARES
                assert [c["class_code"] for c in data["share_classes"]] == ["DPRP-5"]
            finally:
                db.session.remove()
                db.drop_all()


@pytest.mark.unit
class TestCrossProductReferencesRejected:
    """Task 8: 'Block cross-product references on the server.'"""

    def test_funds_url_404s_on_a_shares_fund_id(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                dprp_fund, _ = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-6", currency="USD"
                )
                fund_id = dprp_fund.id

                resp = client.get(f"/api/v1/funds/{fund_id}", headers=get_auth_headers(auth_token))
                assert resp.status_code == 404
            finally:
                db.session.remove()
                db.drop_all()

    def test_shares_url_404s_on_a_funds_fund_id(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                axiom_fund, _ = _make_fund_and_class("Axiom", "AXIOM")
                fund_id = axiom_fund.id

                resp = client.get(f"/api/v1/shares/{fund_id}", headers=get_auth_headers(auth_token))
                assert resp.status_code == 404
            finally:
                db.session.remove()
                db.drop_all()

    def test_add_share_class_rejected_through_wrong_product_url(self, client, super_admin_token, app):
        with app.app_context():
            db.create_all()
            try:
                dprp_fund, _ = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-7", currency="USD"
                )
                fund_id = dprp_fund.id

                # A SHARES fund_id reached through /funds/.../classes (FUNDS-scoped) -> 404.
                resp = client.post(
                    f"/api/v1/funds/{fund_id}/classes",
                    data=json.dumps({"class_name": "Sneaky", "class_code": "SNEAKY-1", "currency": "USD"}),
                    headers={**get_auth_headers(super_admin_token), "Content-Type": "application/json"},
                )
                assert resp.status_code == 404
                assert ShareClass.query.filter_by(class_code="SNEAKY-1").first() is None
            finally:
                db.session.remove()
                db.drop_all()

    def test_funds_fund_class_rejects_ngn_currency(self, client, super_admin_token, app):
        with app.app_context():
            db.create_all()
            try:
                axiom_fund, _ = _make_fund_and_class("Axiom", "AXIOM")
                resp = client.post(
                    f"/api/v1/funds/{axiom_fund.id}/classes",
                    data=json.dumps({"class_name": "Bad", "class_code": "AXM-NGN", "currency": "NGN"}),
                    headers={**get_auth_headers(super_admin_token), "Content-Type": "application/json"},
                )
                assert resp.status_code == 400
            finally:
                db.session.remove()
                db.drop_all()

    def test_shares_fund_class_accepts_ngn_currency(self, client, super_admin_token, app):
        with app.app_context():
            db.create_all()
            try:
                dprp_fund, _ = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-8", currency="USD"
                )
                resp = client.post(
                    f"/api/v1/shares/{dprp_fund.id}/classes",
                    data=json.dumps({"class_name": "New Class", "class_code": "DPRP-NGN", "currency": "NGN"}),
                    headers={**get_auth_headers(super_admin_token), "Content-Type": "application/json"},
                )
                assert resp.status_code == 201
                assert resp.get_json()["data"]["product_type"] == SHARES
            finally:
                db.session.remove()
                db.drop_all()

    def test_share_class_model_rejects_explicit_mismatch(self, app):
        """ShareClass.before_insert: an explicit product_type that disagrees
        with its fund raises, rather than silently drifting."""
        with app.app_context():
            db.create_all()
            try:
                fund = CoreFund(fund_name="Axiom", fund_code="AXIOM", product_type=FUNDS)
                db.session.add(fund)
                db.session.commit()

                bad_class = ShareClass(
                    core_fund_id=fund.id, class_name="Bad", class_code="BAD-CLASS",
                    currency="USD", product_type=SHARES,
                )
                db.session.add(bad_class)
                with pytest.raises(ValueError):
                    db.session.commit()
            finally:
                db.session.rollback()
                db.session.remove()
                db.drop_all()

    def test_batch_model_rejects_explicit_mismatch_with_share_class(self, app):
        """Batch.before_insert: an explicit product_type that disagrees with
        its share class raises — the 'batch product always matches its
        fund's product' consistency check Task 8 asks for."""
        with app.app_context():
            db.create_all()
            try:
                fund = CoreFund(fund_name="Axiom", fund_code="AXIOM", product_type=FUNDS)
                db.session.add(fund)
                db.session.flush()
                share_class = ShareClass(core_fund_id=fund.id, class_name="Axiom Class", class_code="AXM-I", currency="USD")
                db.session.add(share_class)
                db.session.commit()

                bad_batch = Batch(batch_name="Bad Batch", share_class_id=share_class.id, product_type=SHARES)
                db.session.add(bad_batch)
                with pytest.raises(ValueError):
                    db.session.commit()
            finally:
                db.session.rollback()
                db.session.remove()
                db.drop_all()

    def test_create_batch_api_rejects_mismatched_product_type(self, client, auth_token, app):
        """The explicit create-batch endpoint's own validation (app/Batch/
        controllers.py) catches the mismatch with a clean 400, before the
        model-level event would otherwise raise a raw 500."""
        with app.app_context():
            db.create_all()
            try:
                _, share_class = _make_fund_and_class("Axiom", "AXIOM")
                share_class_id = share_class.id

                resp = client.post(
                    "/api/v1/batches",
                    data=json.dumps({
                        "batch_name": "Mismatched Batch",
                        "share_class_id": share_class_id,
                        "product_type": "SHARES",
                    }),
                    headers={**get_auth_headers(auth_token), "Content-Type": "application/json"},
                )
                assert resp.status_code == 400
                assert Batch.query.filter_by(batch_name="Mismatched Batch").first() is None
            finally:
                db.session.remove()
                db.drop_all()


@pytest.mark.unit
class TestFundSummaryByProduct:
    """GET /api/v1/funds/summary vs GET /api/v1/shares/summary."""

    def test_funds_summary_excludes_dprp_shares_summary_includes_only_dprp(self, client, app):
        with app.app_context():
            db.create_all()
            try:
                _make_fund_and_class("Axiom", "AXIOM")
                _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP-9", currency="USD"
                )

                resp = client.get("/api/v1/funds/summary")
                funds_names = [f["fund_name"] for f in resp.get_json()["data"]["funds"]]
                assert "Axiom" in funds_names
                assert "Dangote Petroleum Refinery and Petrochemicals FZE" not in funds_names

                resp = client.get("/api/v1/shares/summary")
                shares_names = [f["fund_name"] for f in resp.get_json()["data"]["funds"]]
                assert shares_names == ["Dangote Petroleum Refinery and Petrochemicals FZE"]
            finally:
                db.session.remove()
                db.drop_all()
