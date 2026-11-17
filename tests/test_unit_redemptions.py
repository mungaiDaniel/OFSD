"""
Unit-based redemptions (NAV funds) — record a withdrawal the way the transfer
agent books it (shares x NAV on the trade date), reduce the client's shares,
and never also subtract the cash from value.

Real case: Janus contract note 6035089 — Mary Mburu redeemed 101.423 shares of
Horizon Biotechnology A2 USD at NAV 37.96 = USD 3,850.00 on 20/10/2026.

Run with: pytest tests/test_unit_redemptions.py -v
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Funds.investor_shares import InvestorShares
from app.Funds.nav_history import NavHistory
from app.Investments.model import Investment, Withdrawal, WithdrawalLot
from app.Valuation.valuation_snapshot import ValuationSnapshot


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _lot(fund, share_class, client, shares, dep_nav, deployed, amount):
    batch = Batch(
        batch_name=f"{client} {deployed}", share_class_id=share_class.id, stage=4, is_active=True,
        deployment_confirmed=True, total_shares=Decimal(shares), deployment_nav=Decimal(dep_nav),
        date_deployed=datetime.combine(deployed, datetime.min.time(), tzinfo=timezone.utc),
    )
    db.session.add(batch)
    db.session.flush()
    inv = Investment(
        investor_name="Mary Mburu", investor_email="mary@example.com", internal_client_code=client,
        amount_deposited=Decimal(amount), batch_id=batch.id, fund_id=fund.id, fund_name=fund.fund_name,
        share_class_id=share_class.id, shares_owned=Decimal(shares),
        date_deposited=datetime.combine(deployed, datetime.min.time(), tzinfo=timezone.utc),
    )
    db.session.add(inv)
    db.session.flush()
    holding = InvestorShares(
        investment_id=inv.id, share_class_id=share_class.id, batch_id=batch.id,
        shares_owned=Decimal(shares), deployment_nav=Decimal(dep_nav), deployment_date=deployed,
    )
    db.session.add(holding)
    db.session.flush()
    return batch, inv, holding


def _seed_biotech(app, lots):
    """lots: list of (shares, dep_nav, deployed_date, amount). Returns ids."""
    with app.app_context():
        fund = CoreFund(fund_name="JANUS HENDERSON HORIZON BIOTECH TEST", fund_code="JHB-T")
        db.session.add(fund)
        db.session.flush()
        sc = ShareClass(core_fund_id=fund.id, class_name="Biotechnology A2", class_code="JH_BIO", currency="USD")
        db.session.add(sc)
        db.session.flush()
        made = [_lot(fund, sc, "145591", *l) for l in lots]
        db.session.commit()
        return {"fund_id": fund.id, "class_id": sc.id,
                "lots": [(b.id, i.id, h.id) for b, i, h in made]}


@pytest.mark.unit
class TestRecordRedemption:
    def test_marys_contract_note_reduces_her_shares(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        body = {
            "client_code": "145591", "fund_id": ids["fund_id"], "share_class_id": ids["class_id"],
            "shares": 101.423, "nav": 37.96, "gross_amount": 3850.00,
            "trade_date": "2026-10-20", "settlement_date": "2026-10-23", "ta_reference": "6035089",
        }
        r = client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token))
        assert r.status_code == 201, r.get_json()

        with app.app_context():
            batch_id, inv_id, holding_id = ids["lots"][0]
            holding = db.session.get(InvestorShares, holding_id)
            assert holding.shares_owned == Decimal("1077.553000")
            assert db.session.get(Investment, inv_id).shares_owned == Decimal("1077.5530")
            assert db.session.get(Batch, batch_id).total_shares == Decimal("1077.553")

            w = db.session.query(Withdrawal).one()
            assert w.status == "Executed"
            assert w.gross_amount == Decimal("3850.00")  # contract-note amount, not 101.423 x 37.96 = 3,850.02
            assert w.amount == Decimal("3850.00")
            assert w.ta_reference == "6035089" and w.trade_date == date(2026, 10, 20)
            lots = db.session.query(WithdrawalLot).all()
            assert len(lots) == 1 and lots[0].shares_redeemed == Decimal("101.423000")

            # A snapshot at the trade date, valued on what's left.
            snap = db.session.query(ValuationSnapshot).filter_by(investor_shares_id=holding_id, valuation_date=date(2026, 10, 20)).one()
            assert snap.shares_held == Decimal("1077.553000")
            assert snap.market_value == Decimal("40903.91")  # 1,077.553 x 37.96

    def test_fifo_across_lots_and_later_snapshot_corrected(self, client, app, auth_token):
        ids = _seed_biotech(app, [
            ("100", "40", date(2026, 3, 1), "4000"),
            ("50", "42", date(2026, 5, 1), "2100"),
        ])
        (b1, _i1, h1), (b2, _i2, h2) = ids["lots"]
        with app.app_context():
            # A valuation dated AFTER the trade date, still on the old share counts.
            db.session.add(ValuationSnapshot(investor_shares_id=h2, valuation_date=date(2026, 10, 30), nav_per_share=Decimal("45"),
                                             shares_held=Decimal("50"), market_value=Decimal("2250.00"), performance_pct=Decimal("0")))
            db.session.commit()

        body = {"client_code": "145591", "fund_id": ids["fund_id"], "shares": 120, "nav": 40, "trade_date": "2026-10-20", "exit_fee": 96}
        r = client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token))
        assert r.status_code == 201, r.get_json()

        with app.app_context():
            first, second = db.session.get(InvestorShares, h1), db.session.get(InvestorShares, h2)
            assert first.shares_owned == 0 and first.is_active is False  # oldest lot emptied first
            assert second.shares_owned == Decimal("30")
            assert db.session.get(Batch, b1).total_shares == 0 and db.session.get(Batch, b2).total_shares == Decimal("30")
            later = db.session.query(ValuationSnapshot).filter_by(investor_shares_id=h2, valuation_date=date(2026, 10, 30)).one()
            assert later.shares_held == Decimal("30") and later.market_value == Decimal("1350.00")
            w = db.session.query(Withdrawal).one()
            assert w.gross_amount == Decimal("4800.00") and w.exit_fee_deducted == Decimal("96.00") and w.amount == Decimal("4704.00")

    @pytest.mark.parametrize("override,message", [
        ({"shares": 2000}, "only holds"),
        ({"gross_amount": 5000}, "doesn't match"),
        ({"nav": 0}, "nav must be greater"),
        ({"trade_date": ""}, "trade_date is required"),
    ])
    def test_bad_input_rejected_and_nothing_changes(self, client, app, auth_token, override, message):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        body = {"client_code": "145591", "fund_id": ids["fund_id"], "shares": 101.423, "nav": 37.96, "trade_date": "2026-10-20", **override}
        r = client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token))
        assert r.status_code == 400 and message in r.get_json()["message"]
        with app.app_context():
            assert db.session.get(InvestorShares, ids["lots"][0][2]).shares_owned == Decimal("1178.976000")
            assert db.session.query(Withdrawal).count() == 0

    def test_executes_an_existing_pending_request(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        with app.app_context():
            w = Withdrawal(internal_client_code="145591", fund_id=ids["fund_id"], gross_amount=Decimal("3850"), amount=Decimal("3850"), status="Pending")
            db.session.add(w)
            db.session.commit()
            wid = w.id
        body = {"withdrawal_id": wid, "shares": 101.423, "nav": 37.96, "gross_amount": 3850, "trade_date": "2026-10-20"}
        r = client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token))
        assert r.status_code == 201, r.get_json()
        with app.app_context():
            assert db.session.query(Withdrawal).count() == 1
            w = db.session.get(Withdrawal, wid)
            assert w.status == "Executed" and w.shares_redeemed == Decimal("101.423000")
        again = client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token))
        assert again.status_code == 400  # can't execute twice


@pytest.mark.unit
class TestNoDoubleCounting:
    def test_fund_summary_value_is_remaining_shares_times_nav(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        with app.app_context():
            db.session.add(NavHistory(share_class_id=ids["class_id"], nav_date=date(2026, 10, 30), nav_per_share=Decimal("39.37"), source="valuation"))
            db.session.commit()
        body = {"client_code": "145591", "fund_id": ids["fund_id"], "shares": 101.423, "nav": 37.96, "gross_amount": 3850, "trade_date": "2026-10-20"}
        assert client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token)).status_code == 201

        funds = client.get("/api/v1/funds/summary").get_json()["data"]["funds"]
        f = next(x for x in funds if x["id"] == ids["fund_id"])
        # Remaining shares x NAV — NOT (shares x NAV) - 3,850. The summary rounds
        # total shares to 2dp before multiplying (existing behaviour): 1,077.55 x 39.37.
        assert f["totals_by_currency"]["USD"] == pytest.approx(round(1077.553, 2) * 39.37, abs=0.02)

    def test_legacy_cash_withdrawal_still_subtracted(self, client, app):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        with app.app_context():
            db.session.add(NavHistory(share_class_id=ids["class_id"], nav_date=date(2026, 10, 30), nav_per_share=Decimal("39.37"), source="valuation"))
            db.session.add(Withdrawal(internal_client_code="145591", fund_id=ids["fund_id"], gross_amount=Decimal("3850"),
                                      amount=Decimal("3850"), status="Approved",
                                      date_withdrawn=datetime(2026, 10, 20, tzinfo=timezone.utc)))
            db.session.commit()
        funds = client.get("/api/v1/funds/summary").get_json()["data"]["funds"]
        f = next(x for x in funds if x["id"] == ids["fund_id"])
        assert f["totals_by_currency"]["USD"] == pytest.approx(round(1178.976, 2) * 39.37 - 3850, abs=0.02)

    def test_statement_shows_redemption_before_that_days_valuation(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        holding_id = ids["lots"][0][2]
        with app.app_context():
            db.session.add(ValuationSnapshot(investor_shares_id=holding_id, valuation_date=date(2026, 10, 7), nav_per_share=Decimal("40"),
                                             shares_held=Decimal("1178.976"), market_value=Decimal("47159.04"), performance_pct=Decimal("0")))
            db.session.commit()
        body = {"client_code": "145591", "fund_id": ids["fund_id"], "shares": 101.423, "nav": 37.96, "gross_amount": 3850, "trade_date": "2026-10-20"}
        assert client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(auth_token)).status_code == 201

        rows = client.get("/api/v1/investors/145591/statements", headers=_headers(auth_token)).get_json()["data"]
        oct20 = [r for r in rows if str(r.get("date", "")).startswith("2026-10-20")]
        red = next(r for r in oct20 if r["type"] == "WITHDRAWAL")
        val = next(r for r in oct20 if r["type"] == "VALUATION")
        assert red["label"] == "Redemption" and red["withdrawals"] == pytest.approx(3850.00)
        assert red["shares"] == pytest.approx(-101.423)
        # Valuation measured on what was left: opening = 47,159.04 - 3,850 = 43,309.04;
        # 1,077.553 x 37.96 = 40,903.91 -> gain -2,405.13 (market move only, not the withdrawal).
        assert val["opening_balance"] == pytest.approx(43309.04)
        assert val["end_balance"] == pytest.approx(40903.91)
        # Deposit row still shows the shares originally allotted.
        dep = next(r for r in rows if r["type"] in ("DEPOSIT", "DEPLOYMENT") and r.get("shares_at_deployment"))
        assert dep["shares_at_deployment"] == pytest.approx(1178.976)


# ── Withdrawal statement PDF + email attachment ──────────────────────────────

def _pdf_text(data):
    from io import BytesIO
    from PyPDF2 import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(data)).pages)


def _record_marys(client, ids, token):
    body = {"client_code": "145591", "fund_id": ids["fund_id"], "shares": 101.423, "nav": 37.96, "gross_amount": 3850,
            "trade_date": "2026-10-20", "settlement_date": "2026-10-23", "ta_reference": "6035089"}
    r = client.post("/api/v1/withdrawals/redemptions", data=json.dumps(body), headers=_headers(token))
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["id"]


@pytest.mark.unit
class TestWithdrawalStatement:
    def test_redemption_statement_shows_contract_note_and_holding(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        wid = _record_marys(client, ids, auth_token)
        # A valuation AFTER the sale: the holding is shown at today's value, not the sale price.
        with app.app_context():
            db.session.add(ValuationSnapshot(investor_shares_id=ids["lots"][0][2], valuation_date=date(2026, 10, 30),
                                             nav_per_share=Decimal("39.37"), shares_held=Decimal("1077.553"),
                                             market_value=Decimal("42423.26"), performance_pct=Decimal("0")))
            db.session.commit()
        r = client.get(f"/api/v1/investors/145591/withdrawals/{wid}/pdf", headers=_headers(auth_token))
        assert r.status_code == 200 and r.data[:4] == b"%PDF"
        text = _pdf_text(r.data)
        for expected in ("Shares Redeemed", "101.4230", "37.9600", "3,850.00", "6035089", "October 20, 2026",
                         "Holding After Withdrawal", "Current Holding (as at 30 Oct 2026)", "1,077.5530", "39.3700", "42,423.26"):
            assert expected in text, expected
        # No before/redeemed/after breakdown at the sale price any more.
        for gone in ("Before Withdrawal", "40,903.91", "44,753.93"):
            assert gone not in text, gone
        from io import BytesIO
        from PyPDF2 import PdfReader
        assert len(PdfReader(BytesIO(r.data)).pages) == 1  # disclaimer no longer spills onto a 2nd page
        # Removed from the statement on request: approval date, status, settlement date.
        for removed in ("Approved Date", "Status", "Settlement Date", "Executed", "October 23, 2026"):
            assert removed not in text, removed

    def test_cash_withdrawal_statement_still_works(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        with app.app_context():
            w = Withdrawal(internal_client_code="145591", fund_id=ids["fund_id"], gross_amount=Decimal("500"), amount=Decimal("500"), status="Approved")
            db.session.add(w)
            db.session.commit()
            wid = w.id
        r = client.get(f"/api/v1/investors/145591/withdrawals/{wid}/pdf", headers=_headers(auth_token))
        assert r.status_code == 200
        text = _pdf_text(r.data)
        assert "Withdrawal Summary" in text and "500.00" in text and "Shares Redeemed" not in text

    def test_other_clients_withdrawal_is_404(self, client, app, auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        wid = _record_marys(client, ids, auth_token)
        assert client.get(f"/api/v1/investors/999999/withdrawals/{wid}/pdf", headers=_headers(auth_token)).status_code == 404


@pytest.mark.unit
class TestWithdrawalEmailAttachment:
    def test_preview_offers_the_statement_and_body_has_redemption_details(self, client, app, auth_token, super_admin_auth_token):
        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        wid = _record_marys(client, ids, auth_token)
        h = _headers(super_admin_auth_token)
        d = client.get(f"/api/v1/emails/bulk-send/sample?kind=withdrawal&fund_id={ids['fund_id']}&client_code=145591", headers=h).get_json()["data"]
        assert d["attachment_name"] == f"withdrawal-statement-145591-{wid}.pdf"
        assert "Shares Redeemed: 101.4230 at NAV 37.9600" in d["body"] and "attached" in d["body"]
        assert "cid:" not in d["html"]  # preview shows the logo inline instead of a broken image
        pdf = client.get(f"/api/v1/emails/bulk-send/sample-pdf?kind=withdrawal&fund_id={ids['fund_id']}&client_code=145591", headers=h)
        assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"

    def test_sent_withdrawal_email_carries_the_statement(self, client, app, auth_token, super_admin_auth_token, monkeypatch):
        from app.Investments.model import PendingEmail
        from app.Investments.route import _send_pending_email_now
        from app.utils.email_service import mail

        ids = _seed_biotech(app, [("1178.976", "43.57", date(2026, 8, 13), "51367.98")])
        wid = _record_marys(client, ids, auth_token)
        r = client.post("/api/v1/emails/bulk-send", json={"kind": "withdrawal", "fund_id": ids["fund_id"], "expected_count": 1},
                        headers=_headers(super_admin_auth_token))
        assert r.status_code == 200, r.get_json()
        email_id = r.get_json()["data"]["email_ids"][0]

        with app.app_context():
            assert db.session.get(PendingEmail, email_id).withdrawal_id == wid
            sent = []
            monkeypatch.setattr(mail, "send", lambda msg: sent.append(msg))
            ok, message, _status = _send_pending_email_now(email_id)
            assert ok, message
            pdfs = [a for a in sent[0].attachments if a.content_type == "application/pdf"]
            assert [a.filename for a in pdfs] == [f"withdrawal-statement-145591-{wid}.pdf"]
            assert "Shares Redeemed" in _pdf_text(pdfs[0].data)
