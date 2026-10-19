"""
SHARES minimum deposit — approved exceptions.

A Shares deposit under MIN_DEPOSIT_USD is rejected unless an admin approves it as an
exception with a reason; the exception is stored and the transfer check then accepts it.

Run with: pytest tests/test_min_deposit_exception.py -v
"""

from decimal import Decimal

import pytest

from app.database.database import db
from app.BulkUpload.route import _validate_row, _commit_bulk_upload_chunk
from app.Batch.core_fund import CoreFund
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment
from app.logic.shares_transfer_service import SharesTransferService, SharesTransferError
from tests.test_shares_transfer_fees import _make_fund_and_class


def _dprp():
    return _make_fund_and_class("Dangote Petroleum Refinery and Petrochemicals FZE", "DPRP", class_code="DPRP")


def _class_lookup(fund, sc):
    return {sc.class_code.lower(): {
        "id": sc.id, "class_code": sc.class_code, "currency": sc.currency,
        "fund_id": fund.id, "fund_name": fund.fund_name, "product_type": fund.product_type,
    }}


def _row(code, amount):
    return {
        "client_code": code, "investor_name": f"Client {code}", "investor_email": f"{code}@example.com",
        "share_class_code": "DPRP", "deposit_amount": amount, "deposit_date": "2026-10-01",
    }


def _commit(rows, fund_id):
    # `rows` as the frontend sends them: a validated row plus optional exception fields.
    return _commit_bulk_upload_chunk(db.session, rows, "t.xlsx", {}, {}, {})


@pytest.mark.unit
class TestMinDepositException:
    def test_validate_flags_below_minimum_rows_only(self, app):
        with app.app_context():
            fund, sc = _dprp()
            db.session.commit()
            lookup = _class_lookup(fund, sc)
            low = _validate_row(_row("151337", "1987.5"), 1, {}, lookup, {})
            ok = _validate_row(_row("999", "2000"), 2, {}, lookup, {})
            assert low["resolved"]["below_minimum"] is True and low["status"] == "valid"
            assert any("exception" in w["message"] for w in low["warnings"])
            assert ok["resolved"]["below_minimum"] is False

    def test_commit_rejects_without_exception_and_accepts_with_reason(self, app):
        with app.app_context():
            fund, sc = _dprp()
            db.session.commit()
            lookup = _class_lookup(fund, sc)
            base = _validate_row(_row("151337", "1987.5"), 1, {}, lookup, {})

            _, failed, _ = _commit([dict(base)], fund.id)
            assert len(failed) == 1 and "exception" in failed[0]["message"]
            db.session.rollback()

            _, failed, _ = _commit([{**base, "min_deposit_exception": True, "min_deposit_exception_reason": "  "}], fund.id)
            assert len(failed) == 1  # a reason is required

            ok, failed, _ = _commit([{**base, "min_deposit_exception": True, "min_deposit_exception_reason": "Bank charges deducted"}], fund.id)
            db.session.commit()
            assert len(ok) == 1 and not failed
            inv = db.session.query(Investment).filter_by(internal_client_code="151337").one()
            assert inv.min_deposit_exception is True and inv.min_deposit_exception_reason == "Bank charges deducted"

    def test_transfer_check_skips_approved_exception_only(self, app):
        with app.app_context():
            fund, sc = _dprp()
            db.session.commit()
            lookup = _class_lookup(fund, sc)
            rows = [
                {**_validate_row(_row("A1", "1987.5"), 1, {}, lookup, {}), "min_deposit_exception": True, "min_deposit_exception_reason": "ok"},
                _validate_row(_row("B1", "1980.4"), 2, {}, lookup, {}),
                _validate_row(_row("C1", "5000"), 3, {}, lookup, {}),
            ]
            _commit(rows, fund.id)
            db.session.commit()
            invs = db.session.query(Investment).order_by(Investment.internal_client_code).all()
            assert [i.internal_client_code for i in invs] == ["A1", "C1"]  # B1 was refused
            # Approved exception no longer blocks the transfer-stage check.
            SharesTransferService.validate_inputs(invs, 0, 10)
            # ...but an unapproved below-minimum deposit still does.
            invs[0].min_deposit_exception = False
            with pytest.raises(SharesTransferError):
                SharesTransferService.validate_inputs(invs, 0, 10)
