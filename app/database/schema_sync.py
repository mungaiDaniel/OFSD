"""Idempotent schema sync run at startup.

Brings a pre-existing database up to date with the models using
``ADD COLUMN IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS`` statements.
The documented, reversible equivalents live in ``migrations/versions``.
"""
from sqlalchemy import text


def sync_schema(db) -> None:
    """Apply all idempotent DDL and backfills, committing at the end."""
    db.session.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
    db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
    db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS queued_at TIMESTAMPTZ"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_pending_emails_queued_at ON pending_emails (queued_at)"))
    db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_email VARCHAR(120)"))
    db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_name VARCHAR(120)"))
    # Add new columns for transfer transaction costs
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS transfer_transaction_cost NUMERIC(20, 2) DEFAULT 0.00"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS transfer_fee_deducted NUMERIC(20, 2) DEFAULT 0.00"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS min_deposit_exception BOOLEAN NOT NULL DEFAULT FALSE"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS min_deposit_exception_reason TEXT"))
    # Manual per-investor "amount received" at the Transfer stage (FUNDS
    # only) — the real amount that landed in the bank for this investor,
    # typed in by hand instead of computed via the pro-rata formula.
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS transfer_amount_received NUMERIC(20, 2)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS share_series VARCHAR(100)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_owned NUMERIC(24, 4)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS original_deposit_amount NUMERIC(20, 2)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS current_market_value NUMERIC(20, 2)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS opening_market_value NUMERIC(20, 2)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS previous_nav_price NUMERIC(20, 6)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS rounding_adjustment NUMERIC(20, 4) DEFAULT 0.0000"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS official_receipt_value NUMERIC(20, 2)"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS deployment_total_nav NUMERIC(20, 2)"))
    db.session.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'currency_type_enum') THEN CREATE TYPE currency_type_enum AS ENUM ('USD','KES','NGN'); END IF; END $$;"))
    # SHARES/DPRP investments are NGN-valued (see migration 020/021) - make sure older DBs accept it.
    db.session.execute(text("ALTER TYPE currency_type_enum ADD VALUE IF NOT EXISTS 'NGN'"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS currency_type currency_type_enum"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS cached_total_capital NUMERIC(20, 2)"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS cached_total_capital_at TIMESTAMPTZ"))
    # investments.internal_client_code is filtered/joined on in nearly every investor-facing
    # route (directory, overview, statements, history, PDF generation) and had no index at
    # all beyond the primary key — was a full table scan on every one of those queries.
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_internal_client_code ON investments (internal_client_code)"))
    # Bulk-upload duplicate detection (and other case-insensitive client-code lookups)
    # filter on lower(internal_client_code), which the plain btree index above can't
    # serve — Postgres can't use an index on a raw column to satisfy a query wrapped
    # in a function, so every such lookup was a full table scan under the hood despite
    # looking indexed. This functional index lets Postgres index-scan those instead.
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_lower_client_code ON investments (lower(internal_client_code))"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_batch_id ON investments (batch_id)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_fund_id ON investments (fund_id)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_date_deposited ON investments (date_deposited)"))
    # DPRP oversubscription pro-rata allocation
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS oversubscription_refund_amount NUMERIC(20, 2) DEFAULT 0.00"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS is_oversubscribed BOOLEAN DEFAULT FALSE"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS allocation_rate NUMERIC(7, 4)"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'investor_request'"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_withdrawals_source ON withdrawals (source)"))
    # Same functional-index fix as ix_investments_lower_client_code above,
    # for the client-activity/overview queries that also filter withdrawals
    # by func.lower(internal_client_code).
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_withdrawals_lower_client_code ON withdrawals (lower(internal_client_code))"))
    # One-time Oversubscription/Refund Notice tracking (see
    # EmailService.send_oversubscription_refund_notices) — NULL until sent.
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS oversubscription_notice_sent_at TIMESTAMPTZ"))
    # Unit-based redemptions (NAV funds) — see app/logic/redemption_service.py.
    # The withdrawal_lots table itself is created by db.create_all() above.
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS shares_redeemed NUMERIC(24, 6)"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS redemption_nav NUMERIC(20, 6)"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS share_class_id INTEGER REFERENCES share_classes(id) ON DELETE SET NULL"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS trade_date DATE"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS settlement_date DATE"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS ta_reference VARCHAR(50)"))
    db.session.execute(text("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ"))
    # Withdrawal notice emails remember their withdrawal, to attach its statement PDF.
    db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS withdrawal_id INTEGER REFERENCES withdrawals(id) ON DELETE SET NULL"))
    # Multi-fund statement scope: which fund(s) an INVESTOR_STATEMENT
    # PendingEmail was queued for — comma-separated CoreFund ids, or NULL
    # for a full consolidated statement. Set at queue time, read back at
    # send time so the attached PDF matches what was actually approved.
    db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS statement_fund_ids VARCHAR(255)"))
    # Gatekeeper user fields (safe, idempotent)
    db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"))
    db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'"))

    # FUNDS vs SHARES product_type (see app.database.product_type / migration
    # 017_add_product_type). Schema + backfill both repeated here, idempotently,
    # because this startup sync — not `flask db upgrade` — is what actually keeps
    # a running production DB in sync with the models in this app.
    db.session.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'product_type_enum') THEN
                CREATE TYPE product_type_enum AS ENUM ('FUNDS', 'SHARES');
            END IF;
        END $$;
    """))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS product_type product_type_enum"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS product_type product_type_enum"))
    db.session.execute(text("""
        UPDATE batches b
        SET product_type = 'SHARES'
        FROM share_classes sc JOIN core_funds cf ON cf.id = sc.core_fund_id
        WHERE b.share_class_id = sc.id AND b.product_type IS NULL
          AND (UPPER(COALESCE(cf.fund_code, '')) = 'DPRP'
               OR LOWER(COALESCE(cf.fund_name, '')) LIKE '%dangote%'
               OR LOWER(COALESCE(cf.fund_name, '')) LIKE '%dprp%')
    """))
    db.session.execute(text("UPDATE batches SET product_type = 'FUNDS' WHERE product_type IS NULL"))
    db.session.execute(text("""
        UPDATE investments i SET product_type = b.product_type
        FROM batches b WHERE i.batch_id = b.id AND i.product_type IS NULL
    """))
    db.session.execute(text("UPDATE investments SET product_type = 'FUNDS' WHERE product_type IS NULL"))
    db.session.execute(text("ALTER TABLE batches ALTER COLUMN product_type SET NOT NULL"))
    db.session.execute(text("ALTER TABLE batches ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    db.session.execute(text("ALTER TABLE investments ALTER COLUMN product_type SET NOT NULL"))
    db.session.execute(text("ALTER TABLE investments ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_batches_product_type ON batches (product_type)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_investments_product_type ON investments (product_type)"))

    # SHARES Transferred-stage fees (Task 2 — app.logic.shares_transfer_service).
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS balance_after_entry_fee_usd NUMERIC(20, 2)"))

    # SHARES Deployed-stage USD->NGN allocation (Task 3 — app.logic.shares_deployment_service).
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_exchange_rate_ngn NUMERIC(20, 6)"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_price_per_share_ngn NUMERIC(20, 4)"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_allocated_total INTEGER"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_demand_total INTEGER"))
    db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS shares_unallocated_total INTEGER"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_exchange_rate_ngn NUMERIC(20, 6)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS shares_price_per_share_ngn NUMERIC(20, 4)"))
    db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS net_ngn NUMERIC(20, 2)"))

    # Task 8: FUNDS vs SHARES product_type moves up to the fund level —
    # core_funds.product_type is now the authoritative source (ShareClass/
    # Batch/Investment each inherit and validate against the row above them;
    # see the before_insert events in their model files). Schema + backfill
    # repeated here idempotently for the same reason as the Task 1 block
    # above: this startup sync, not `flask db upgrade`, is what keeps a
    # running production DB in sync with the models in this app — see
    # migration 020_add_fund_product_type for the documented/reversible
    # Alembic-script equivalent of this same change.
    db.session.execute(text("ALTER TABLE core_funds ADD COLUMN IF NOT EXISTS product_type product_type_enum"))
    # Task 12: optional fund/share description (editable on the detail page).
    db.session.execute(text("ALTER TABLE core_funds ADD COLUMN IF NOT EXISTS description TEXT"))
    db.session.execute(text("""
        UPDATE core_funds
        SET product_type = 'SHARES'
        WHERE product_type IS NULL
          AND (UPPER(COALESCE(fund_code, '')) = 'DPRP'
               OR LOWER(COALESCE(fund_name, '')) LIKE '%dangote%'
               OR LOWER(COALESCE(fund_name, '')) LIKE '%dprp%')
    """))
    db.session.execute(text("UPDATE core_funds SET product_type = 'FUNDS' WHERE product_type IS NULL"))
    db.session.execute(text("ALTER TABLE core_funds ALTER COLUMN product_type SET NOT NULL"))
    db.session.execute(text("ALTER TABLE core_funds ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_core_funds_product_type ON core_funds (product_type)"))

    db.session.execute(text("ALTER TABLE share_classes ADD COLUMN IF NOT EXISTS product_type product_type_enum"))
    db.session.execute(text("""
        UPDATE share_classes sc
        SET product_type = cf.product_type
        FROM core_funds cf
        WHERE sc.core_fund_id = cf.id AND sc.product_type IS NULL
    """))
    db.session.execute(text("UPDATE share_classes SET product_type = 'FUNDS' WHERE product_type IS NULL"))
    db.session.execute(text("ALTER TABLE share_classes ALTER COLUMN product_type SET NOT NULL"))
    db.session.execute(text("ALTER TABLE share_classes ALTER COLUMN product_type SET DEFAULT 'FUNDS'"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_share_classes_product_type ON share_classes (product_type)"))

    # Currency: share classes may be KES/USD/NGN (SHARES classes may use
    # any of them, FUNDS stay KES/USD — enforced per product in
    # app/Funds/edit_service.py::CURRENCIES_BY_PRODUCT). SHARES deposits
    # are USD; the one-time NGN -> USD relabel is migration 023, so the
    # class currency is no longer forced here on every start.
    db.session.execute(text("ALTER TABLE share_classes DROP CONSTRAINT IF EXISTS _currency_check"))
    db.session.execute(text("ALTER TABLE share_classes ADD CONSTRAINT _currency_check CHECK (currency IN ('KES', 'USD', 'NGN'))"))

    # Commit everything above before the optional legacy-column backfill below, so that
    # if it fails it can't silently discard all the schema-sync statements that already
    # succeeded in this same transaction (see rollback() in the except branch — Postgres
    # aborts the whole transaction on error, and without a rollback the later commit()
    # was quietly reverting all of it with no visible error).
    db.session.commit()

    # Backfill role from legacy column if present
    try:
        db.session.execute(text("""
            UPDATE "user"
            SET role = CASE
                WHEN COALESCE(role, '') = '' THEN COALESCE(NULLIF(user_role, ''), 'user')
                ELSE role
            END
        """))
        # no-op if already canonical; keep for safety
        db.session.execute(text("UPDATE \"user\" SET role='super_admin' WHERE role='superadmin'"))
        db.session.commit()
    except Exception:
        # Legacy user_role column doesn't exist on this DB — nothing to backfill.
        db.session.rollback()

