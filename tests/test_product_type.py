"""
Product Type (FUNDS vs SHARES) Tests
=====================================
Covers Task 1: separating SHARES (DPRP) from FUNDS at the batch/deposit level.

- Migration backfill: counts preserved, DPRP rows become SHARES.
- API: product filter on batch/investor/deposit list endpoints.
- Cross-product deposit is rejected on the server.
- One investor can hold both FUNDS and SHARES at the same time.

Run with: pytest tests/test_product_type.py -v
"""

import importlib.util
import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database.database import db
from app.database.product_type import FUNDS, SHARES
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment
from app.logic.batch_management_service import BatchManagementService


def get_auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


def _load_migration_017():
    """Load migrations/versions/017_add_product_type.py by path — its filename
    starts with a digit, so it isn't importable as a normal dotted module."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "migrations", "versions", "017_add_product_type.py")
    spec = importlib.util.spec_from_file_location("migration_017_add_product_type", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_fund_and_class(fund_name, fund_code, class_code="CI-USD", currency="USD"):
    fund = CoreFund(fund_name=fund_name, fund_code=fund_code)
    db.session.add(fund)
    db.session.flush()  # need fund.id before the FK on ShareClass
    share_class = ShareClass(
        core_fund_id=fund.id,
        class_name=f"{fund_name} Class",
        class_code=class_code,
        currency=currency,
    )
    db.session.add(share_class)
    db.session.flush()
    return fund, share_class


def _make_investment(batch, client_code, name="Test Investor", amount="1000.00", **kwargs):
    investment = Investment(
        batch_id=batch.id,
        investor_name=name,
        investor_email=f"{client_code.lower()}@example.com",
        internal_client_code=client_code,
        amount_deposited=Decimal(amount),
        share_class_id=batch.share_class_id,
        **kwargs,
    )
    db.session.add(investment)
    db.session.commit()
    return investment


class TestProductTypeModel:
    """Batches/investments resolve and inherit product_type correctly."""

    def test_axiom_batch_defaults_to_funds(self, app):
        with app.app_context():
            db.create_all()
            try:
                _, share_class = _make_fund_and_class("Axiom", "AXIOM")
                batch = BatchManagementService.find_or_create_batch(share_class.id)
                assert batch.product_type == FUNDS
            finally:
                db.session.remove()
                db.drop_all()

    def test_dprp_batch_resolves_to_shares(self, app):
        with app.app_context():
            db.create_all()
            try:
                _, share_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                batch = BatchManagementService.find_or_create_batch(share_class.id)
                assert batch.product_type == SHARES
            finally:
                db.session.remove()
                db.drop_all()

    def test_investment_inherits_product_type_from_batch(self, app):
        with app.app_context():
            db.create_all()
            try:
                _, share_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                batch = BatchManagementService.find_or_create_batch(share_class.id)
                investment = _make_investment(batch, "CLIENT-SHARES-1")
                assert investment.product_type == SHARES
            finally:
                db.session.remove()
                db.drop_all()

    def test_cross_product_deposit_is_rejected(self, app):
        """A SHARES deposit cannot be added to a FUNDS batch, and vice versa."""
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)

                # A deposit built for the SHARES share class ...
                mismatched = Investment(
                    investor_name="Mismatch",
                    investor_email="mismatch@example.com",
                    internal_client_code="CLIENT-MIX-1",
                    amount_deposited=Decimal("500.00"),
                    share_class_id=shares_class.id,
                    product_type=SHARES,
                )
                # ... cannot be added to the FUNDS batch.
                with pytest.raises(ValueError):
                    BatchManagementService.add_investor_to_batch(mismatched, funds_batch)
            finally:
                db.session.remove()
                db.drop_all()

    def test_investor_can_hold_both_products(self, app):
        """One internal_client_code can have both a FUNDS and a SHARES holding."""
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)

                code = "CLIENT-BOTH-1"
                _make_investment(funds_batch, code, amount="1000.00")
                _make_investment(shares_batch, code, amount="2000.00")

                rows = Investment.query.filter_by(internal_client_code=code).all()
                assert len(rows) == 2
                assert {r.product_type for r in rows} == {FUNDS, SHARES}
                # Still a single investor identity — no duplicated investor record exists.
                names = {r.internal_client_code for r in rows}
                assert names == {code}
            finally:
                db.session.remove()
                db.drop_all()


class TestProductTypeMigrationBackfill:
    """Exercises the real migration 017 backfill SQL against seed-like data."""

    def test_backfill_preserves_counts_and_tags_dprp_as_shares(self, app):
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)

                _make_investment(funds_batch, "CLIENT-F1")
                _make_investment(funds_batch, "CLIENT-F2")
                _make_investment(shares_batch, "CLIENT-S1")

                before_batch_count = Batch.query.count()
                before_investment_count = Investment.query.count()

                conn = db.session.connection()
                # Simulate the moment right after `ADD COLUMN product_type` in the
                # real migration, before its backfill UPDATEs run.
                conn.execute(text("ALTER TABLE batches ALTER COLUMN product_type DROP NOT NULL"))
                conn.execute(text("ALTER TABLE investments ALTER COLUMN product_type DROP NOT NULL"))
                conn.execute(text("UPDATE batches SET product_type = NULL"))
                conn.execute(text("UPDATE investments SET product_type = NULL"))

                migration = _load_migration_017()
                migration._backfill_product_type(conn)

                # Restore NOT NULL (same transaction/connection as the backfill —
                # db.session.commit() below returns `conn` to the pool, so it can't
                # be reused afterward) so later assertions see the normal, migrated
                # schema shape.
                conn.execute(text("ALTER TABLE batches ALTER COLUMN product_type SET NOT NULL"))
                conn.execute(text("ALTER TABLE investments ALTER COLUMN product_type SET NOT NULL"))

                db.session.commit()
                db.session.expire_all()

                assert Batch.query.count() == before_batch_count
                assert Investment.query.count() == before_investment_count

                assert db.session.get(Batch, funds_batch.id).product_type == FUNDS
                assert db.session.get(Batch, shares_batch.id).product_type == SHARES

                investments_by_code = {
                    inv.internal_client_code: inv.product_type
                    for inv in Investment.query.all()
                }
                assert investments_by_code["CLIENT-F1"] == FUNDS
                assert investments_by_code["CLIENT-F2"] == FUNDS
                assert investments_by_code["CLIENT-S1"] == SHARES
            finally:
                db.session.remove()
                db.drop_all()

    def test_backfill_count_summary_matches_before_and_after(self, app):
        """_print_product_type_counts totals add up to the same row counts before/after."""
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Atium", "ATIUM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)
                _make_investment(funds_batch, "CLIENT-A1")
                _make_investment(shares_batch, "CLIENT-A2")

                conn = db.session.connection()
                migration = _load_migration_017()
                counts = migration._print_product_type_counts(conn, "unit test")

                assert sum(counts["batches"].values()) == Batch.query.count()
                assert sum(counts["investments"].values()) == Investment.query.count()
                assert counts["batches"].get(SHARES, 0) == 1
                assert counts["investments"].get(SHARES, 0) == 1
            finally:
                db.session.remove()
                db.drop_all()


class TestProductTypeApiFilters:
    """product=FUNDS|SHARES filters on the list endpoints."""

    def test_batches_list_product_filter(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)
                _make_investment(funds_batch, "CLIENT-BF1")
                _make_investment(shares_batch, "CLIENT-BS1")

                resp = client.get(
                    '/api/v1/batches?product=SHARES',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 200
                data = resp.get_json()["data"]
                assert len(data) == 1
                assert data[0]["id"] == shares_batch.id
                assert data[0]["product_type"] == SHARES

                resp_all = client.get('/api/v1/batches', headers=get_auth_headers(auth_token))
                assert resp_all.status_code == 200
                assert len(resp_all.get_json()["data"]) == 2
            finally:
                db.session.remove()
                db.drop_all()

    def test_investor_directory_product_filter(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)

                _make_investment(funds_batch, "CLIENT-D1", name="Funds Only")
                _make_investment(shares_batch, "CLIENT-D2", name="Shares Only")
                _make_investment(funds_batch, "CLIENT-D3", name="Both Products")
                _make_investment(shares_batch, "CLIENT-D3", name="Both Products")

                resp = client.get(
                    '/api/v1/investors?product=SHARES',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 200
                codes = {row["internal_client_code"] for row in resp.get_json()["data"]}
                assert codes == {"CLIENT-D2", "CLIENT-D3"}

                resp_all = client.get('/api/v1/investors', headers=get_auth_headers(auth_token))
                codes_all = {row["internal_client_code"] for row in resp_all.get_json()["data"]}
                assert codes_all == {"CLIENT-D1", "CLIENT-D2", "CLIENT-D3"}
            finally:
                db.session.remove()
                db.drop_all()

    def test_investor_deposits_product_filter(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                funds_batch = BatchManagementService.find_or_create_batch(funds_class.id)
                shares_batch = BatchManagementService.find_or_create_batch(shares_class.id)

                code = "CLIENT-DEP-1"
                _make_investment(funds_batch, code, amount="1000.00")
                _make_investment(shares_batch, code, amount="2000.00")

                resp = client.get(
                    f'/api/v1/investors/{code}/deposits?product=FUNDS',
                    headers=get_auth_headers(auth_token),
                )
                assert resp.status_code == 200
                rows = resp.get_json()["data"]
                assert len(rows) == 1
                assert rows[0]["product_type"] == FUNDS

                resp_all = client.get(
                    f'/api/v1/investors/{code}/deposits',
                    headers=get_auth_headers(auth_token),
                )
                assert len(resp_all.get_json()["data"]) == 2
            finally:
                db.session.remove()
                db.drop_all()


class TestCreateBatchProductType:
    """POST /api/v1/batches resolves and validates product_type."""

    def test_create_batch_with_dprp_share_class_resolves_shares(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _, shares_class = _make_fund_and_class(
                    "Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP"
                )
                db.session.commit()
                payload = {"batch_name": "DPRP-MANUAL-1", "share_class_id": shares_class.id}
                resp = client.post(
                    '/api/v1/batches',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 201
                assert resp.get_json()["data"]["product_type"] == SHARES
            finally:
                db.session.remove()
                db.drop_all()

    def test_create_batch_product_type_mismatch_rejected(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                _, funds_class = _make_fund_and_class("Axiom", "AXIOM")
                db.session.commit()
                payload = {
                    "batch_name": "AXIOM-MANUAL-1",
                    "share_class_id": funds_class.id,
                    "product_type": "SHARES",
                }
                resp = client.post(
                    '/api/v1/batches',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 400
            finally:
                db.session.remove()
                db.drop_all()

    def test_create_batch_without_share_class_defaults_to_funds(self, client, auth_token, app):
        with app.app_context():
            db.create_all()
            try:
                payload = {"batch_name": "TWO-STAGE-1"}
                resp = client.post(
                    '/api/v1/batches',
                    data=json.dumps(payload),
                    headers={**get_auth_headers(auth_token), 'Content-Type': 'application/json'},
                )
                assert resp.status_code == 201
                assert resp.get_json()["data"]["product_type"] == FUNDS
            finally:
                db.session.remove()
                db.drop_all()
