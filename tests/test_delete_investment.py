"""
Delete investment (Transfer/Show-all "delete investor") — super_admin only
=============================================================================
DELETE /api/v1/investments/<id> permanently removes one deposit row.
Covers:
* role check (non super_admin -> 403, no row deleted)
* success path (super_admin -> 204, row gone)
* related rows that FK to investments.id WITHOUT ondelete=CASCADE
  (pending_emails, email_logs, report_recipients + orphaned report_runs,
  investment_batch_valuations, pro_rata_distribution) are cleaned up first,
  so the delete doesn't blow up with a FK violation
* investor_shares (ondelete=CASCADE in the DB, but cleaned up explicitly too)
  are gone afterward
* batch.cached_total_capital is refreshed after the delete
* an audit log entry is written

Run with: pytest tests/test_delete_investment.py -v
"""

import json
from decimal import Decimal

import pytest

from app.database.database import db
from app.Admin.model import User
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Funds.investor_shares import InvestorShares
from app.Investments.model import Investment, PendingEmail, EmailLog
from app.Reports.model import ReportRun, ReportRecipient
from app.Valuation.model import InvestmentBatchValuation
from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
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
        _make_user("super_admin", "del_super@example.com")
        return create_access_token(identity="del_super@example.com", additional_claims={"admin": 2})


@pytest.fixture
def admin_token(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        _make_user("admin", "del_admin@example.com")
        return create_access_token(identity="del_admin@example.com", additional_claims={"admin": 1})


def _seed_investment(app):
    with app.app_context():
        fund = CoreFund(fund_name="Delete Test Fund", fund_code="DEL")
        db.session.add(fund)
        db.session.flush()
        share_class = ShareClass(core_fund_id=fund.id, class_name="Delete Class", class_code="DEL-I", currency="USD")
        db.session.add(share_class)
        db.session.flush()
        batch = Batch(batch_name="Delete Test Batch", share_class_id=share_class.id, stage=1, is_active=True)
        db.session.add(batch)
        db.session.flush()
        inv = Investment(
            investor_name="To Be Deleted",
            investor_email="deleteme@example.com",
            internal_client_code="DEL-1",
            amount_deposited=Decimal("1000.00"),
            batch_id=batch.id,
            fund_id=fund.id,
            share_class_id=share_class.id,
        )
        db.session.add(inv)
        db.session.commit()
        db.session.refresh(inv)
        return inv.id, batch.id


@pytest.mark.unit
class TestDeleteInvestment:
    def test_non_super_admin_forbidden(self, client, app, admin_token):
        investment_id, _ = _seed_investment(app)
        r = client.delete(f"/api/v1/investments/{investment_id}", headers=_headers(admin_token))
        assert r.status_code == 403
        with app.app_context():
            assert db.session.get(Investment, investment_id) is not None

    def test_super_admin_deletes_investment(self, client, app, super_admin_token):
        investment_id, batch_id = _seed_investment(app)
        r = client.delete(f"/api/v1/investments/{investment_id}", headers=_headers(super_admin_token))
        assert r.status_code == 204
        with app.app_context():
            assert db.session.get(Investment, investment_id) is None

    def test_related_rows_cleaned_up_without_fk_violation(self, client, app, super_admin_token):
        investment_id, batch_id = _seed_investment(app)
        with app.app_context():
            batch = db.session.get(Batch, batch_id)
            inv = db.session.get(Investment, investment_id)

            db.session.add(PendingEmail(
                batch_id=batch_id, investor_id=investment_id, email_type="DEPOSIT_CONFIRMATION",
                status="Pending_Confirmation", subject="s", body="b", recipient_email="x@example.com",
            ))
            db.session.add(EmailLog(investor_id=investment_id, batch_id=batch_id, status="Sent"))
            db.session.add(InvestorShares(
                investment_id=investment_id, share_class_id=inv.share_class_id, batch_id=batch_id,
                shares_owned=Decimal("10.0000"), deployment_nav=Decimal("100.0000"),
                deployment_date=db.func.current_date(),
            ))
            db.session.add(InvestmentBatchValuation(
                investment_id=investment_id, batch_id=batch_id, period_end_date=db.func.now(),
                balance_at_end_of_period=Decimal("1000.00"), net_principal_snapshot=Decimal("1000.00"),
            ))
            performance = Performance(batch_id=batch_id, fund_name="Delete Test Fund", gross_profit=Decimal("0.00"))
            db.session.add(performance)
            db.session.flush()
            db.session.add(ProRataDistribution(
                investment_id=investment_id, batch_id=batch_id, fund_name="Delete Test Fund",
                performance_id=performance.id, profit_allocated=Decimal("0.00"),
            ))
            run = ReportRun(period="2026-01", share_class_id=inv.share_class_id, fund_id=inv.fund_id, sent_by="x@example.com")
            db.session.add(run)
            db.session.flush()
            db.session.add(ReportRecipient(report_run_id=run.id, investor_id=investment_id, investor_email="x@example.com"))
            db.session.commit()
            run_id = run.id

        r = client.delete(f"/api/v1/investments/{investment_id}", headers=_headers(super_admin_token))
        assert r.status_code == 204

        with app.app_context():
            assert db.session.get(Investment, investment_id) is None
            assert db.session.query(PendingEmail).filter(PendingEmail.investor_id == investment_id).count() == 0
            assert db.session.query(EmailLog).filter(EmailLog.investor_id == investment_id).count() == 0
            assert db.session.query(InvestorShares).filter(InvestorShares.investment_id == investment_id).count() == 0
            assert db.session.query(InvestmentBatchValuation).filter(InvestmentBatchValuation.investment_id == investment_id).count() == 0
            assert db.session.query(ProRataDistribution).filter(ProRataDistribution.investment_id == investment_id).count() == 0
            assert db.session.query(ReportRecipient).filter(ReportRecipient.investor_id == investment_id).count() == 0
            # The report run had exactly this one recipient -> now orphaned -> cleaned up too.
            assert db.session.get(ReportRun, run_id) is None

    def test_batch_cached_total_capital_refreshed(self, client, app, super_admin_token):
        investment_id, batch_id = _seed_investment(app)
        with app.app_context():
            batch = db.session.get(Batch, batch_id)
            batch.cached_total_capital = Decimal("999999.00")
            db.session.commit()

        r = client.delete(f"/api/v1/investments/{investment_id}", headers=_headers(super_admin_token))
        assert r.status_code == 204

        with app.app_context():
            batch = db.session.get(Batch, batch_id)
            assert batch.cached_total_capital != Decimal("999999.00")

    def test_audit_log_written(self, client, app, super_admin_token):
        investment_id, batch_id = _seed_investment(app)
        r = client.delete(f"/api/v1/investments/{investment_id}", headers=_headers(super_admin_token))
        assert r.status_code == 204

        with app.app_context():
            log = db.session.query(AuditLog).filter(
                AuditLog.action == "DELETE_INVESTMENT",
                AuditLog.target_id == investment_id,
            ).first()
            assert log is not None
            assert log.target_name == "To Be Deleted"
            assert log.user_email == "del_super@example.com"

    def test_not_found_returns_404(self, client, app, super_admin_token):
        r = client.delete("/api/v1/investments/999999", headers=_headers(super_admin_token))
        assert r.status_code == 404
