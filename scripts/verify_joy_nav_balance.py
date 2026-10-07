from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from app.database.database import db
from app.Batch.model import Batch
from app.Batch.controllers import BatchController
from app.Investments.model import Investment
from app.Valuation.model import DailyNAV


JOY_NAME = "Joy Kendi Muthuri"
TARGET_SHARES = Decimal("771.92")
TARGET_NAV = Decimal("1389.5737")
TARGET_DATE = datetime(2026, 4, 10, tzinfo=timezone.utc)
SERIES = "Class I - KES"


def q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_schema():
    db.session.execute(
        text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_owned NUMERIC(24, 8)")
    )
    db.session.execute(
        text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS share_series VARCHAR(100)")
    )
    db.session.execute(
        text(
            "ALTER TABLE investment_batch_valuations ADD COLUMN IF NOT EXISTS nav_at_period_end NUMERIC(24, 8)"
        )
    )
    db.session.execute(
        text(
            "ALTER TABLE investment_batch_valuations ADD COLUMN IF NOT EXISTS total_shares_at_time NUMERIC(24, 8)"
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS daily_nav (
                id SERIAL PRIMARY KEY,
                nav_date TIMESTAMPTZ NOT NULL,
                share_series VARCHAR(100) NOT NULL,
                nav_price NUMERIC(24, 8) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT _daily_nav_date_series_uc UNIQUE (nav_date, share_series)
            )
            """
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_daily_nav_series_date ON daily_nav (share_series, nav_date)"
        )
    )
    db.session.commit()


def run():
    ensure_schema()

    joy_rows = (
        db.session.query(Investment)
        .filter(Investment.investor_name.ilike(f"%{JOY_NAME}%"))
        .order_by(Investment.id.asc())
        .all()
    )
    if not joy_rows:
        print(f"No investment rows found for '{JOY_NAME}'.")
        return

    joy = joy_rows[0]
    batch = db.session.query(Batch).filter(Batch.id == joy.batch_id).first()
    if not batch:
        print(f"Joy row found (id={joy.id}) but batch not found.")
        return

    joy.shares_owned = TARGET_SHARES
    joy.share_series = SERIES
    db.session.add(joy)

    nav_row = (
        db.session.query(DailyNAV)
        .filter(DailyNAV.share_series == SERIES, DailyNAV.nav_date == TARGET_DATE)
        .first()
    )
    if nav_row is None:
        nav_row = DailyNAV(nav_date=TARGET_DATE, share_series=SERIES, nav_price=TARGET_NAV)
    else:
        nav_row.nav_price = TARGET_NAV
    db.session.add(nav_row)
    db.session.commit()

    values = BatchController._calculate_batch_investment_values(joy, batch, db.session)

    raw = q2(TARGET_SHARES * TARGET_NAV)
    print("=== NAV Test Result ===")
    print(f"Investor row id: {joy.id}")
    print(f"Batch id/name: {batch.id} / {batch.batch_name}")
    print(f"shares_owned set: {TARGET_SHARES}")
    print(f"NAV set ({SERIES}, {TARGET_DATE.date()}): {TARGET_NAV}")
    print(f"Raw shares*NAV: {raw}")
    print(f"Controller current_balance: {values.get('current_balance')}")
    print(f"Controller profit: {values.get('profit')}")
    print(f"Controller performance_pct: {values.get('performance_pct')}")
    print(f"Controller purchase_nav: {values.get('purchase_nav')}")
    print(f"Controller current_nav: {values.get('current_nav')}")


if __name__ == "__main__":
    with app.app_context():
        run()
