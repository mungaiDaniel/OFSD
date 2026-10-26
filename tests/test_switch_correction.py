"""
Switch correction: fix one holding's shares / NAV / date after a class switch.

Run with: pytest tests/test_switch_correction.py -v
"""

from datetime import date
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.model import Batch
from app.Funds.investor_shares import InvestorShares
from app.Investments.model import Investment
from app.Investments.route import get_investor_statements
from app.utils.switch_correction import apply_switch_correction, SwitchCorrectionError
from app.Valuation.valuation_snapshot import ValuationSnapshot
from tests.test_valuation_date_edit_and_split_rows import _seed, _add_second_client


def _batch():
    return db.session.query(Batch).first()


@pytest.mark.unit
class TestSwitchCorrection:
    def test_dry_run_saves_nothing(self, app):
        with app.app_context():
            _seed(date(2026, 7, 10), date(2026, 7, 27), [date(2026, 9, 10)])
            b = _batch()
            r = apply_switch_correction(db.session, b.id, "50", "45", date(2026, 8, 10), expected_value="2250")
            assert r["applied"] is False
            assert r["after"]["holding"]["shares_owned"] == "50"
            h = db.session.query(InvestorShares).one()
            assert h.shares_owned == Decimal("59.1739") and h.deployment_date == date(2026, 7, 27)

    def test_apply_fixes_holding_snapshot_batch_and_statement(self, app):
        with app.app_context():
            _seed(date(2026, 7, 10), date(2026, 7, 27), [date(2026, 9, 10)])
            b = _batch()
            r = apply_switch_correction(db.session, b.id, "50", "45", date(2026, 8, 10), expected_value="2250", apply=True)
            assert r["applied"] is True
            db.session.expire_all()

            h = db.session.query(InvestorShares).one()
            assert (h.shares_owned, h.deployment_nav, h.deployment_date) == (Decimal("50"), Decimal("45"), date(2026, 8, 10))
            inv = db.session.query(Investment).one()
            assert inv.shares_owned == Decimal("50") and inv.opening_market_value == Decimal("2250.00")
            assert inv.amount_deposited == Decimal("2433.23")  # cost is untouched
            b = _batch()
            assert (b.total_shares, b.deployment_total_nav, b.deployment_date_actual) == (Decimal("50"), Decimal("2250.00"), date(2026, 8, 10))

            snap = db.session.query(ValuationSnapshot).one()
            assert snap.shares_held == Decimal("50") and snap.market_value == Decimal("1918.50")
            assert snap.nav_per_share == Decimal("38.37") and snap.performance_pct == Decimal("-14.7333")

            rows = get_investor_statements.__wrapped__("EDIT-1").get_json()["data"]
            dep = [x for x in rows if x["type"] == "DEPLOYMENT"][0]
            assert dep["date"][:10] == "2026-08-10" and dep["shares"] == 50.0 and dep["nav_per_share"] == 45.0

    def test_refuses_unsafe_requests(self, app):
        with app.app_context():
            _seed(date(2026, 7, 10), date(2026, 7, 27), [date(2026, 8, 1), date(2026, 9, 10)])
            b = _batch()
            with pytest.raises(SwitchCorrectionError, match="before the switch date"):
                apply_switch_correction(db.session, b.id, "50", "45", date(2026, 8, 10), apply=True)
            with pytest.raises(SwitchCorrectionError, match="expected value"):
                apply_switch_correction(db.session, b.id, "50", "45", date(2026, 7, 28), expected_value="9999", apply=True)
            with pytest.raises(SwitchCorrectionError, match="future"):
                apply_switch_correction(db.session, b.id, "50", "45", date(2999, 1, 1), apply=True)
            h = db.session.query(InvestorShares).one()
            assert h.shares_owned == Decimal("59.1739")  # nothing changed

    def test_refuses_batch_with_other_clients(self, app):
        with app.app_context():
            sc_id = _seed(date(2026, 7, 10), date(2026, 7, 27), [])
            b = _batch()
            _add_second_client(b.id, b.share_class.core_fund_id, sc_id, date(2026, 7, 11), date(2026, 7, 27))
            with pytest.raises(SwitchCorrectionError, match="single-investment|pass investment_id"):
                apply_switch_correction(db.session, b.id, "50", "45", date(2026, 8, 10), apply=True)
