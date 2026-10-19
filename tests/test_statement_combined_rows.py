"""
Investor statement — one valuation row per date, one section per class
=============================================================================
Display-only changes to the statement PDF (no figures change):
1. Each deposit is its own holding, so the data has one VALUATION row per
   deposit per valuation date. The table now shows them as ONE combined
   "Valuations" row per date (sums; Perf % = combined gain / combined
   previous value).
2. A client holding two classes of one fund (e.g. JH_BT and JH_GT) gets a
   separate Account Summary + Statements table per class, instead of one
   blended summary and one table mixing both classes' rows.

Run with: pytest tests/test_statement_combined_rows.py -v
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from PyPDF2 import PdfReader

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Funds.investor_shares import InvestorShares
from app.Investments.model import Investment
from app.Valuation.valuation_snapshot import ValuationSnapshot
from app.Investments.route import _combine_same_day_valuation_rows, _generate_investor_statement_pdf_bytes


def _val(date_str, shares, nav, opening, profit, end, perf):
    return {
        "type": "VALUATION", "date": date_str, "currency": "USD", "shares": shares, "nav_per_share": nav,
        "opening_balance": opening, "profit": profit, "end_balance": end, "performance_rate": perf,
        "deposits": 0.0, "withdrawals": 0.0,
    }


class TestCombineSameDayValuationRows:
    def test_three_deposits_valued_same_day_become_one_row(self):
        # The 10 Sep 2026 rows from the client statement screenshot.
        rows = [
            _val("2026-09-10", 183.4601, 15.9, 2682.22, 234.80, 2917.02, 7.34),
            _val("2026-09-10", 70.0750, 15.9, 1024.51, 89.68, 1114.19, 3.41),
            _val("2026-09-10", 100.2082, 15.9, 1468.32, 124.99, 1593.31, 8.51),
            {"type": "DEPOSIT", "date": "2026-07-27", "currency": "USD", "deposits": 1468.32},
        ]
        out = _combine_same_day_valuation_rows(rows)

        assert len(out) == 2
        v = out[0]
        assert v["type"] == "VALUATION"
        assert v["shares"] == pytest.approx(353.7433)
        assert v["nav_per_share"] == 15.9
        assert v["opening_balance"] == pytest.approx(5175.05)
        assert v["profit"] == pytest.approx(449.47)
        assert v["end_balance"] == pytest.approx(5624.52)  # = the statement's Market Value
        assert v["performance_rate"] == pytest.approx(8.69)  # 449.47 / 5175.05
        # Deposit rows are untouched and keep their position.
        assert out[1] is rows[3]

    def test_different_dates_or_navs_are_not_merged(self):
        rows = [
            _val("2026-09-10", 10, 15.9, 100, 5, 105, 5),
            _val("2026-07-22", 10, 14.62, 100, -1, 99, -1),
            _val("2026-09-10", 10, 31.5, 300, 9, 309, 3),  # another class's NAV that day
        ]
        assert len(_combine_same_day_valuation_rows(rows)) == 3

    def test_totals_are_unchanged_by_combining(self):
        rows = [
            _val("2026-09-10", 183.4601, 15.9, 2682.22, 234.80, 2917.02, 7.34),
            _val("2026-09-10", 70.0750, 15.9, 1024.51, 89.68, 1114.19, 3.41),
            _val("2026-07-22", 183.4601, 14.6202, 2780.83, -98.61, 2682.22, -1.30),
            _val("2026-07-22", 70.0750, 14.6202, 1062.18, -37.67, 1024.51, -4.91),
        ]
        out = _combine_same_day_valuation_rows(rows)
        for key in ("profit", "end_balance", "opening_balance"):
            assert sum(r[key] for r in out) == pytest.approx(sum(r[key] for r in rows))


def _pdf_text(buf):
    buf.seek(0)
    return "\n".join(page.extract_text() or "" for page in PdfReader(buf).pages)


def _holding(client_code, fund, share_class, deposit, shares, dep_nav, val_nav, deposited, valued):
    batch = Batch(
        batch_name=f"{share_class.class_code} {deposited:%b}", share_class_id=share_class.id, stage=4,
        is_active=True, deployment_confirmed=True, date_deployed=datetime.combine(deposited, datetime.min.time(), tzinfo=timezone.utc),
    )
    db.session.add(batch)
    db.session.flush()
    inv = Investment(
        investor_name="Two Class Client", investor_email="twoclass@example.com", internal_client_code=client_code,
        amount_deposited=Decimal(deposit), batch_id=batch.id, fund_id=fund.id, fund_name=fund.fund_name,
        share_class_id=share_class.id, date_deposited=datetime.combine(deposited, datetime.min.time(), tzinfo=timezone.utc),
    )
    db.session.add(inv)
    db.session.flush()
    holding = InvestorShares(
        investment_id=inv.id, share_class_id=share_class.id, batch_id=batch.id,
        shares_owned=Decimal(shares), deployment_nav=Decimal(dep_nav), deployment_date=deposited,
    )
    db.session.add(holding)
    db.session.flush()
    db.session.add(ValuationSnapshot(
        investor_shares_id=holding.id, valuation_date=valued, nav_per_share=Decimal(val_nav),
        shares_held=Decimal(shares), market_value=(Decimal(shares) * Decimal(val_nav)).quantize(Decimal("0.01")),
        performance_pct=Decimal("0"),
    ))


@pytest.mark.unit
def test_two_class_client_gets_a_section_per_class_with_one_valuation_row_each(app):
    with app.app_context():
        fund = CoreFund(fund_name="Janus Henderson", fund_code="JH-TEST")
        db.session.add(fund)
        db.session.flush()
        bt = ShareClass(core_fund_id=fund.id, class_name="Balanced", class_code="JH_BT", currency="USD")
        gt = ShareClass(core_fund_id=fund.id, class_name="Global Tech", class_code="JH_GT", currency="USD")
        db.session.add_all([bt, gt])
        db.session.flush()

        valued = date(2026, 9, 10)
        # Two JH_BT deposits valued on the same day -> one combined row; one JH_GT deposit.
        _holding("TWOCLASS-1", fund, bt, "1000.00", "100.0000", "10.0000", "10.5000", date(2026, 3, 9), valued)
        _holding("TWOCLASS-1", fund, bt, "500.00", "50.0000", "10.0000", "10.5000", date(2026, 5, 11), valued)
        _holding("TWOCLASS-1", fund, gt, "2000.00", "80.0000", "25.0000", "31.5000", date(2026, 4, 2), valued)
        db.session.commit()

        buf = _generate_investor_statement_pdf_bytes("TWOCLASS-1", fund_ids=[fund.id])
        assert not isinstance(buf, tuple) and buf is not None
        text = _pdf_text(buf)

        assert "Account Summary (Balanced, USD)" in text
        assert "Account Summary (Global Tech, USD)" in text
        assert "Statements (Balanced)" in text and "Statements (Global Tech)" in text
        # One valuation row per class for 10 Sep (was three: one per deposit).
        assert text.count("Valuations") == 2
        # JH_BT combined: 150 shares, value 1,575.00 (=1,050 + 525).
        assert "150.00" in text and "1,575.00" in text
