"""
Investor Statement — Combined Funds + Shares Sections (Task 5)
================================================================
A single investor statement (PDF, Excel, and the emailed attachment) must
show Funds and Shares holdings as two separate sections, never mixing a
Funds USD figure with a Shares NGN figure into one total, and omitting
whichever section the investor has no holdings in.

Covers: funds-only investor, shares-only investor, investor with both —
plus the shared-attachment path (_send_pending_email_now) and the Excel
sheet set, since both read from the same combined-statement machinery.

Run with: pytest tests/test_statement_sections.py -v
"""

from datetime import datetime, timezone, date
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest
from PyPDF2 import PdfReader

from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Investments.model import Investment, EpochLedger, PendingEmail
from app.Investments.route import _generate_investor_statement_pdf_bytes, _send_pending_email_now
from app.logic.batch_management_service import BatchManagementService
from app.logic.shares_transfer_service import SharesTransferService
from app.logic.shares_deployment_service import SharesDeploymentService
from app.utils.email_service import mail


def get_auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


def _pdf_text(pdf_buffer):
    pdf_buffer.seek(0)
    reader = PdfReader(pdf_buffer)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _make_funds_holding(client_code, investor_name="Funds Investor", fund_name="Atium"):
    """
    One plain NAV-based FUNDS holding with a committed epoch — the minimal
    known-good setup mirrored from
    test_investors.py::test_investor_directory_counts_post_epoch_deposits,
    so _append_fund_statement_section has real portfolio data to render.
    """
    fund = CoreFund(fund_name=fund_name)
    db.session.add(fund)
    db.session.flush()

    batch = Batch(batch_name=f"{fund_name} Batch 1", date_deployed=datetime(2026, 4, 1, tzinfo=timezone.utc))
    db.session.add(batch)
    db.session.flush()

    inv = Investment(
        investor_name=investor_name,
        investor_email=f"{client_code.lower()}@example.com",
        internal_client_code=client_code,
        amount_deposited=Decimal("50000.00"),
        date_deposited=datetime(2026, 4, 6, tzinfo=timezone.utc),
        batch_id=batch.id,
        fund_id=fund.id,
        fund_name=fund.fund_name,
    )
    db.session.add(inv)
    db.session.flush()

    ledger = EpochLedger(
        internal_client_code=client_code,
        fund_name=fund_name,
        epoch_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
        epoch_end=datetime(2026, 8, 31, tzinfo=timezone.utc),
        performance_rate=Decimal("0.21185700"),
        start_balance=Decimal("50000.00"),
        deposits=Decimal("0.00"),
        withdrawals=Decimal("0.00"),
        profit=Decimal("10592.81"),
        end_balance=Decimal("60592.81"),
        previous_hash="prevhash",
        current_hash=f"hash-{client_code}",
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(ledger)
    db.session.commit()
    return fund, batch, inv


def _make_dprp_fund_and_batch():
    fund = CoreFund(fund_name="Dangote Petroleum Refinery and Petrochemicals FZE", fund_code="DPRP")
    db.session.add(fund)
    db.session.flush()
    share_class = ShareClass(core_fund_id=fund.id, class_name="DPRP Class", class_code="DPRP", currency="USD")
    db.session.add(share_class)
    db.session.flush()
    batch = BatchManagementService.find_or_create_batch(share_class.id)
    return fund, batch


def _make_shares_holding(client_code, investor_name="Shares Investor", deposit="2000.00", shares_allocated="100000"):
    """
    One SHARES (DPRP) holding, fully transferred and deployed via the real
    Task 2/3 services. Task 7: price_per_share_ngn only determines how many
    whole shares get bought here — the holding is then valued shares x NAV
    per share (NGN) exactly like a FUNDS holding (see
    app.Investments.route._resolve_shares_nav_for_investment), via the
    InvestorShares row apply_to_batch creates. shares_allocated controls
    whether this single investor is fully or over-subscribed:
      "100000" (>> demand) -> fully subscribed, refund_usd == 0.
      "3000" (< demand ~5542) -> oversubscribed, nonzero refund + a Pending
      oversubscription-refund Withdrawal auto-created by apply_to_batch.
    """
    fund, batch = _make_dprp_fund_and_batch()

    inv = Investment(
        investor_name=investor_name,
        investor_email=f"{client_code.lower()}@example.com",
        internal_client_code=client_code,
        amount_deposited=Decimal(deposit),
        date_deposited=datetime(2026, 5, 1, tzinfo=timezone.utc),
        batch_id=batch.id,
        fund_id=fund.id,
        fund_name=fund.fund_name,
        share_class_id=batch.share_class_id,
    )
    db.session.add(inv)
    db.session.commit()

    SharesTransferService.apply_to_batch(batch, db.session, entry_fee_percent="2", total_transaction_cost_usd="20")
    db.session.expire_all()
    batch = db.session.get(Batch, batch.id)
    batch.date_deployed = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db.session.commit()
    SharesDeploymentService.apply_to_batch(
        batch, db.session, exchange_rate="1500", price_per_share_ngn="525", shares_allocated=shares_allocated,
    )
    db.session.commit()
    db.session.expire_all()
    return fund, batch, db.session.get(Investment, inv.id)


@pytest.mark.unit
class TestCombinedStatementPdf:

    def test_funds_only_investor_statement_shows_only_funds_section(self, app):
        with app.app_context():
            client_code = "FUNDS-ONLY-1"
            _make_funds_holding(client_code)

            result = _generate_investor_statement_pdf_bytes(client_code)
            assert isinstance(result, BytesIO), f"expected a PDF buffer, got {result!r}"
            text = _pdf_text(result)

            # The FUNDS section renders (NAV-based Account Summary).
            assert "Account Summary" in text
            assert "ATIUM" in text.upper()

            # No Shares holdings -> the Shares section must be entirely omitted,
            # and a single-product statement never shows a redundant top-level
            # "FUNDS" heading (both_sections_present is False).
            assert "SHARES (DANGOTE PETROLEUM REFINERY IPO)" not in text
            assert "NAV / Share" not in text
            assert "Shares Allocated" not in text

    def test_shares_only_investor_statement_not_valued_yet(self, app):
        """Task 7: before any NAV valuation is committed for the share class,
        the Shares section shows "Not valued yet" rather than a stale
        deployment-price "value" (the old, wrong price-per-share model)."""
        with app.app_context():
            client_code = "SHARES-ONLY-1"
            # Under-subscribed on purpose to also exercise the refund fields.
            _make_shares_holding(client_code, shares_allocated="3000")

            result = _generate_investor_statement_pdf_bytes(client_code)
            assert isinstance(result, BytesIO), f"expected a PDF buffer, got {result!r}"
            text = _pdf_text(result)

            assert "SHARES (DANGOTE PETROLEUM REFINERY IPO)" in text
            assert "NAV / Share (NGN)" in text
            assert "Market Value (NGN)" in text
            assert "Gain / Loss (NGN)" in text
            assert "Shares Allocated" in text
            assert "Exchange Rate Used" in text
            assert "Not valued yet" in text
            assert "Price Per Share" not in text
            # Oversubscribed -> a nonzero refund with an auto-created Pending withdrawal.
            assert "Refund (USD)" in text
            assert "Pending" in text

            # No Funds holdings -> the NAV-based section/heading must be entirely
            # omitted, and never a bare "FUNDS" heading either.
            assert "Account Summary" not in text
            assert "\nFUNDS\n" not in text

    def test_shares_only_investor_statement_after_valuation(self, app):
        """Task 7: once a NAV valuation is committed for the share class,
        market value = shares x NAV/share, cost basis = net NGN deployed,
        gain/loss = market value - cost basis."""
        with app.app_context():
            from app.Funds.nav_history import NavHistory

            client_code = "SHARES-VALUED-1"
            fund, batch, inv = _make_shares_holding(client_code, shares_allocated="100000")

            db.session.add(NavHistory(
                share_class_id=inv.share_class_id, nav_date=date(2026, 7, 1),
                nav_per_share=Decimal("600.00"), source="valuation",
            ))
            db.session.commit()

            result = _generate_investor_statement_pdf_bytes(client_code)
            text = _pdf_text(result)

            assert "Not valued yet" not in text
            assert "NGN 600.0000" in text  # NAV / Share
            # shares_owned (5,542) x 600 = 3,325,200.00; cost basis (net NGN) 2,910,000.00
            assert "NGN 3,325,200.00" in text  # Market Value
            assert "NGN 415,200.00" in text  # Gain/Loss

    def test_investor_with_both_shows_both_sections_never_mixed(self, app):
        with app.app_context():
            client_code = "BOTH-HOLDINGS-1"
            _make_funds_holding(client_code, fund_name="Atium")
            _make_shares_holding(client_code, shares_allocated="100000")

            result = _generate_investor_statement_pdf_bytes(client_code)
            assert isinstance(result, BytesIO), f"expected a PDF buffer, got {result!r}"
            text = _pdf_text(result)

            # Both sections present -> explicit top-level headings for each.
            assert "FUNDS" in text
            assert "SHARES (DANGOTE PETROLEUM REFINERY IPO)" in text
            assert "Account Summary" in text
            assert "NAV / Share (NGN)" in text
            assert "Market Value (NGN)" in text
            assert "Shares Allocated" in text

            # No refund this time (fully subscribed) -> no stray "Refund" row content.
            assert "Net (NGN)" in text
            assert "Net (USD)" in text


@pytest.mark.unit
class TestCombinedStatementExcel:

    def _workbook(self, client, auth_token, client_code):
        response = client.get(
            f'/api/v1/investors/{client_code}/statement/excel',
            headers=get_auth_headers(auth_token),
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        return openpyxl.load_workbook(BytesIO(response.data))

    def test_funds_only_excel_omits_shares_sheet(self, client, auth_token, app):
        with app.app_context():
            client_code = "FUNDS-ONLY-XL-1"
            _make_funds_holding(client_code)

        wb = self._workbook(client, auth_token, client_code)
        assert "Portfolio Summary" in wb.sheetnames
        assert "Statement Timeline" in wb.sheetnames
        assert "Shares Holdings" not in wb.sheetnames

    def test_shares_only_excel_omits_funds_sheets(self, client, auth_token, app):
        with app.app_context():
            client_code = "SHARES-ONLY-XL-1"
            _make_shares_holding(client_code)

        wb = self._workbook(client, auth_token, client_code)
        assert "Shares Holdings" in wb.sheetnames
        assert "Portfolio Summary" not in wb.sheetnames
        assert "Statement Timeline" not in wb.sheetnames

        ws = wb["Shares Holdings"]
        headers = [c.value for c in ws[1]]
        assert "NAV / Share (NGN)" in headers
        assert "Market Value (NGN)" in headers
        assert "Shares Allocated" in headers
        assert "Net (USD)" in headers

    def test_both_holdings_excel_has_all_sheets(self, client, auth_token, app):
        with app.app_context():
            client_code = "BOTH-HOLDINGS-XL-1"
            _make_funds_holding(client_code, fund_name="Atium")
            _make_shares_holding(client_code)

        wb = self._workbook(client, auth_token, client_code)
        assert "Portfolio Summary" in wb.sheetnames
        assert "Statement Timeline" in wb.sheetnames
        assert "Shares Holdings" in wb.sheetnames


@pytest.mark.unit
class TestCombinedStatementEmailAttachment:
    """
    Statements stay a shared feature: one email per investor, with the
    combined PDF attached at send time via _send_pending_email_now (the
    scheduler's own send path, used for both single and bulk/segmented
    queued statement emails) — per Task 5's rule that sending/queueing
    itself is otherwise unchanged.
    """

    def test_combined_statement_email_attaches_both_sections(self, app, monkeypatch):
        with app.app_context():
            client_code = "BOTH-EMAIL-1"
            _, _, funds_inv = _make_funds_holding(client_code, fund_name="Atium")
            _make_shares_holding(client_code)

            sent_messages = []
            monkeypatch.setattr(mail, "send", lambda msg: sent_messages.append(msg))

            pending = PendingEmail(
                investor_id=funds_inv.id,
                email_type="INVESTOR_STATEMENT",
                status="Pending_Confirmation",
                subject="Your Investor Statement is Ready",
                body="Dear Investor, ...",
                recipient_email=funds_inv.investor_email,
                recipient_name=funds_inv.investor_name,
            )
            db.session.add(pending)
            db.session.commit()

            send_ok, message, http_status = _send_pending_email_now(pending.id)
            assert send_ok, message
            assert len(sent_messages) == 1

            msg = sent_messages[0]
            pdf_attachments = [a for a in msg.attachments if a.content_type == "application/pdf"]
            assert len(pdf_attachments) == 1, [a.content_type for a in msg.attachments]
            attachment_text = _pdf_text(BytesIO(pdf_attachments[0].data))
            assert "FUNDS" in attachment_text
            assert "SHARES (DANGOTE PETROLEUM REFINERY IPO)" in attachment_text
