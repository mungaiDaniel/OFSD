import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.database.database import db
from app.Batch.fund_routes import CoreFund
from app.Batch.model import Batch
from app.Investments.model import Investment, EpochLedger, Withdrawal
from app.Valuation.model import ValuationRun


def get_auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
def test_overview_stats_uses_latest_committed_ledger_balances(client, auth_token, app):
    with app.app_context():
        axiom = CoreFund(fund_name="Axiom", fund_code="AX-2026-01")
        atium = CoreFund(fund_name="Atium", fund_code="AT-2026-01")
        db.session.add_all([axiom, atium])
        db.session.commit()

        batch = Batch(batch_name="Overview Total Fix", certificate_number="FIX-OV1")
        db.session.add(batch)
        db.session.commit()

        inv_axiom = Investment(
            investor_name="Axiom Investor",
            investor_email="axiom@example.com",
            internal_client_code="INV-AX-001",
            amount_deposited=Decimal("150000.00"),
            date_deposited=datetime.now(timezone.utc),
            batch_id=batch.id,
            fund_id=axiom.id,
        )
        inv_atium = Investment(
            investor_name="Atium Investor",
            investor_email="atium@example.com",
            internal_client_code="INV-AT-001",
            amount_deposited=Decimal("100000.00"),
            date_deposited=datetime.now(timezone.utc),
            batch_id=batch.id,
            fund_id=atium.id,
        )
        db.session.add_all([inv_axiom, inv_atium])
        db.session.commit()

        run_a = ValuationRun(
            core_fund_id=axiom.id,
            epoch_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
            epoch_end=datetime(2026, 4, 30, tzinfo=timezone.utc),
            performance_rate=Decimal("0.087177"),
            head_office_total=Decimal("163076.60"),
            status="Committed",
        )
        run_b = ValuationRun(
            core_fund_id=atium.id,
            epoch_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
            epoch_end=datetime(2026, 4, 30, tzinfo=timezone.utc),
            performance_rate=Decimal("0.056107"),
            head_office_total=Decimal("105610.70"),
            status="Committed",
        )
        db.session.add_all([run_a, run_b])
        db.session.commit()

        ledger_a = EpochLedger(
            internal_client_code="INV-AX-001",
            fund_name=axiom.fund_name,
            epoch_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
            epoch_end=datetime(2026, 4, 30, tzinfo=timezone.utc),
            performance_rate=Decimal("0.087177"),
            start_balance=Decimal("150000.00"),
            deposits=Decimal("0.00"),
            withdrawals=Decimal("0.00"),
            profit=Decimal("13076.60"),
            end_balance=Decimal("163076.60"),
            previous_hash="a" * 64,
            current_hash="b" * 64,
        )
        ledger_b = EpochLedger(
            internal_client_code="INV-AT-001",
            fund_name=atium.fund_name,
            epoch_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
            epoch_end=datetime(2026, 4, 30, tzinfo=timezone.utc),
            performance_rate=Decimal("0.056107"),
            start_balance=Decimal("100000.00"),
            deposits=Decimal("0.00"),
            withdrawals=Decimal("0.00"),
            profit=Decimal("5610.70"),
            end_balance=Decimal("105610.70"),
            previous_hash="c" * 64,
            current_hash="d" * 64,
        )
        db.session.add_all([ledger_a, ledger_b])
        db.session.commit()

    response = client.get(
        '/api/v1/stats/overview',
        headers=get_auth_headers(auth_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == 200
    data = payload["data"]

    assert data["total_aum"] == 268687.3
    assert data["total_profit"] == 18687.3
    assert data["performance_pct"] == 7.47
    assert data["total_investors"] == 2
    assert data["active_batches"] == 2


@pytest.mark.unit
def test_overview_stats_includes_non_committed_investments(client, auth_token, app):
    with app.app_context():
        fund = CoreFund(fund_name="Fresh Batch Fund", fund_code="FB-2026-01")
        db.session.add(fund)
        batch = Batch(batch_name="Fresh Batch", certificate_number="FIX-FRESH-1")
        db.session.add(batch)
        db.session.commit()

        inv = Investment(
            investor_name="Fresh Investor",
            investor_email="fresh@example.com",
            internal_client_code="INV-FRESH-001",
            amount_deposited=Decimal("250000.00"),
            date_deposited=datetime(2026, 9, 15, tzinfo=timezone.utc),
            batch_id=batch.id,
            fund_id=fund.id,
        )
        db.session.add(inv)
        db.session.commit()

    response = client.get(
        '/api/v1/stats/overview',
        headers=get_auth_headers(auth_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == 200
    data = payload["data"]

    assert data["total_aum"] == 250000.0
    assert data["total_profit"] == 0.0
    assert data["performance_pct"] == 0.0
    assert data["total_investors"] == 1
    assert any(point["deposits"] == 250000.0 for point in data["flow_series"])


@pytest.mark.unit
def test_overview_stats_reflects_post_epoch_approved_withdrawals(client, auth_token, app):
    with app.app_context():
        fund = CoreFund(fund_name="Flow Test Fund", fund_code="FT-2026-01")
        db.session.add(fund)
        batch = Batch(batch_name="Flow Withdrawal Fix", certificate_number="FIX-FLOW-1")
        db.session.add(batch)
        db.session.commit()

        inv = Investment(
            investor_name="Flow Investor",
            investor_email="flow@example.com",
            internal_client_code="INV-FLOW-001",
            amount_deposited=Decimal("200000.00"),
            date_deposited=datetime(2026, 6, 1, tzinfo=timezone.utc),
            batch_id=batch.id,
            fund_id=fund.id,
        )
        db.session.add(inv)
        db.session.commit()

        ledger = EpochLedger(
            internal_client_code="INV-FLOW-001",
            fund_name=fund.fund_name,
            epoch_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            epoch_end=datetime(2026, 6, 30, tzinfo=timezone.utc),
            performance_rate=Decimal("0.00"),
            start_balance=Decimal("274622.00"),
            deposits=Decimal("0.00"),
            withdrawals=Decimal("0.00"),
            profit=Decimal("0.00"),
            end_balance=Decimal("274622.00"),
            previous_hash="a" * 64,
            current_hash="b" * 64,
        )
        db.session.add(ledger)
        db.session.commit()

        withdrawal = Withdrawal(
            internal_client_code="INV-FLOW-001",
            fund_id=fund.id,
            fund_name=fund.fund_name,
            amount=Decimal("54000.00"),
            date_withdrawn=datetime(2026, 7, 1, tzinfo=timezone.utc),
            status="Approved",
            approved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        db.session.add(withdrawal)
        db.session.commit()

    response = client.get(
        '/api/v1/stats/overview',
        headers=get_auth_headers(auth_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    data = payload["data"]

    assert data["total_aum"] == 220622.0
    assert any(point["withdrawals"] == 54000.0 for point in data["flow_series"])
