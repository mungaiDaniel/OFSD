import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from flask_migrate import Migrate
from config import DevelopmentConfig as Config
from app.database.database import db
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt_identity, decode_token
from datetime import timedelta, datetime, timezone
from app.Admin.route import user_v1
from app.Batch.route import batch_v1
from app.Batch.fund_routes import fund_v1
from app.Funds.routes import funds_v1
from app.Investments.route import investment_v1
from app.Performance.route import performance_v1
from app.Valuation.route import valuation_v1
from app.Reports.route import reports_v1
from app.Stats.route import stats_v1
from app.Audit.route import audit_v1
from app.Backup.route import backup_v1
from app.BulkUpload.route import bulk_upload_v1
from app.Settings.route import settings_v1
from app.utils.email_service import EmailService
from app.logic.batch_scheduler_service import BatchSchedulerService
from app.logic.backup_scheduler_service import BackupSchedulerService
from app.logic.email_queue_scheduler_service import EmailQueueSchedulerService
from sqlalchemy import text, func
from app.Admin.model import User
from app.Reports.model import ReportRun, ReportRecipient
from app.utils.audit_log import AuditLog, create_audit_log



def create_app(config_filename):
        app = Flask(__name__)
        app.config.from_object(config_filename)
        app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
        app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=1)
        app.config["JWT_QUERY_STRING_NAME"] = "token"
        app.config["JWT_TOKEN_LOCATION"] = ["headers", "query_string"]
        jwt = JWTManager(app)
        # Explicitly allow frontend origin to fix "Origin not allowed" when supports_credentials is True
        CORS(app, supports_credentials=True, resources={r"/*": {"origins": [
            "http://localhost:5173", 
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "https://osfmr2.aib-axysafrica.com",
            "http://osfmr2.aib-axysafrica.com",
            "https://osfmr.aib-axysafrica.com",
            "http://osfmr.aib-axysafrica.com"
        ]}})
        db.init_app(app)
        # Registers `flask db <command>` (upgrade/current/history/...) — this
        # was never wired up before, which is why those commands didn't exist.
        # Doesn't change any runtime behavior; only adds the CLI commands.
        Migrate(app, db)
        EmailService.init_app(app)
        app.app_context().push()
        db.create_all()

        # Layer any DB-saved Settings -> Email Sending overrides on top of the
        # config.py/.env baseline, and refresh Flask-Mail's cached connection
        # state to match (see app/Settings/service.py — Flask-Mail caches its
        # SMTP config at init_app() time, so this is what makes a saved
        # settings change actually take effect on the next email sent).
        try:
            from app.Settings.service import apply_email_settings_to_app
            apply_email_settings_to_app(app, db.session)
        except Exception as e:
            print(f"Applying saved email settings failed (using config.py/.env values): {str(e)}")

        # Flask's debug-mode auto-reloader runs this whole module TWICE: once in a
        # parent "watcher" process that just restarts the child on file changes,
        # and once in the actual worker child that serves requests. Since app =
        # create_app(...) runs at import time (not inside `if __name__ ==
        # "__main__"`), both processes were starting their own independent
        # BackgroundScheduler — which is exactly how the same queued email got
        # sent twice (two schedulers, each polling the same 'Queued' rows).
        # WERKZEUG_RUN_MAIN is only set in the worker child, so this guard makes
        # sure schedulers start there exactly once, not in the watcher too.
        # In production (debug=False, no reloader) this is always true.
        is_reloader_parent = app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
        if is_reloader_parent:
            print("Reloader watcher process detected — skipping scheduler startup here (worker process will start them).")
        else:
            # Schema-sync DDL (ALTER TABLE/CREATE INDEX ... IF NOT EXISTS) — moved inside
            # this same is_reloader_parent guard as the schedulers above, for the same
            # reason: this whole module runs twice under the debug reloader (watcher +
            # worker), and two processes running dozens of ALTER TABLE/CREATE INDEX
            # statements concurrently is a real Postgres deadlock, not just wasted work —
            # confirmed live (DeadlockDetected between two overlapping runs of this exact
            # block during ordinary dev editing). Running it only in the worker process
            # (or the single process in production, where is_reloader_parent is always
            # False) makes it run exactly once per actual server start.
            db.session.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
            db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
            db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS queued_at TIMESTAMPTZ"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_pending_emails_queued_at ON pending_emails (queued_at)"))
            db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_email VARCHAR(120)"))
            db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_name VARCHAR(120)"))
            # Add new columns for transfer transaction costs
            db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS transfer_transaction_cost NUMERIC(20, 2) DEFAULT 0.00"))
            db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS transfer_fee_deducted NUMERIC(20, 2) DEFAULT 0.00"))
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

            # Initialize batch scheduler
            try:
                BatchSchedulerService.init_scheduler(app)
                print("Batch scheduler initialized")
            except Exception as e:
                print(f"Batch scheduler initialization failed: {str(e)}")

            if app.config.get("DB_BACKUP_ENABLED"):
                try:
                    BackupSchedulerService.init_scheduler(app)
                    print("Backup scheduler initialized")
                except Exception as e:
                    print(f"Backup scheduler initialization failed: {str(e)}")

            try:
                EmailQueueSchedulerService.init_scheduler(app)
                print("Email send queue scheduler initialized")
            except Exception as e:
                print(f"Email send queue scheduler initialization failed: {str(e)}")

            # Recover bulk-upload commit jobs from before a restart. APScheduler's
            # BackgroundScheduler is in-memory only — a job scheduled with
            # trigger="date" that hasn't fired yet is simply gone after a restart/deploy.
            # A 'running' job means it was actually interrupted mid-commit: some rows
            # in it may already be committed, so it's marked 'failed' rather than
            # silently re-run (which would risk double-committing the rows that made
            # it through before the restart). A 'queued' job never started, so nothing
            # was written for it yet — safe to just re-schedule from scratch.
            try:
                from app.BulkUpload.model import BulkUploadJob
                from app.BulkUpload.route import _run_bulk_upload_commit_job
                interrupted = db.session.query(BulkUploadJob).filter(BulkUploadJob.status == "running").all()
                for job in interrupted:
                    job.status = "failed"
                    job.error_message = (
                        "Interrupted by a server restart. processed_rows/succeeded_count "
                        "show how far it got — check those rows exist before re-uploading "
                        "the remainder, to avoid double-creating them."
                    )
                    job.completed_at = datetime.now(timezone.utc)
                requeued = db.session.query(BulkUploadJob).filter(BulkUploadJob.status == "queued").all()
                db.session.commit()
                for job in requeued:
                    BatchSchedulerService.scheduler.add_job(
                        func=_run_bulk_upload_commit_job,
                        args=[app, job.id],
                        trigger="date",
                        run_date=datetime.now(timezone.utc),
                        id=f"bulk_upload_job_{job.id}",
                        misfire_grace_time=3600,
                        max_instances=1,
                        replace_existing=True,
                    )
                if interrupted or requeued:
                    print(f"Bulk upload job recovery: {len(interrupted)} marked failed (interrupted), {len(requeued)} re-scheduled")
            except Exception as e:
                print(f"Bulk upload job recovery failed: {str(e)}")

        # Gatekeeper enforcement:
        # - If a user is logged in (valid JWT) but status != active, block API calls.
        # - This forces immediate logout on the frontend (we treat this as auth invalidation).
        @app.before_request
        def _gatekeeper_active_user():
            path = request.path or ""
            if not path.startswith("/api/v1"):
                return None

            # Never gatekeep CORS preflight
            if request.method == "OPTIONS":
                return None

            # Allow auth + public endpoints through
            if path in ("/api/v1/login", "/api/v1/users"):
                return None

            # Only enforce when a JWT is present/required
            try:
                verify_jwt_in_request(optional=True)
                identity = get_jwt_identity()
            except Exception:
                # No/invalid JWT in request context — let route-level jwt_required handle it
                return None
            if not identity:
                return None

            # identity is email string in your tokens
            if isinstance(identity, dict):
                identity = identity.get("email")
            normalized_identity = str(identity or "").strip().lower()
            if not normalized_identity:
                return None
            user = User.query.filter(func.lower(User.email) == normalized_identity).first()
            if user and getattr(user, "status", "active") != "active":
                return make_response(jsonify({
                    "status": 401,
                    "message": "Your account is pending administrator approval."
                }), 401)

        @app.after_request
        def _audit_mutations(response):
            try:
                path = request.path or ""
                if not path.startswith("/api/v1"):
                    return response
                if request.method in ("GET", "OPTIONS"):
                    return response
                # Avoid logging the audit endpoint itself to prevent recursion/noise
                if path.startswith("/api/v1/audit-logs"):
                    return response

                # Attempt to attach identity (optional)
                identity_email = None
                actor_id = None
                actor_name = None
                try:
                    verify_jwt_in_request(optional=True)
                    identity_email = get_jwt_identity()
                    # Backward compat: older tokens stored identity payload as {"email": "..."}
                    if isinstance(identity_email, dict):
                        identity_email = identity_email.get("email")
                    if isinstance(identity_email, str) and identity_email.strip():
                        identity_email = identity_email.strip().lower()
                        actor = User.query.filter(func.lower(User.email) == identity_email).first()
                        if actor:
                            actor_id = actor.id
                            actor_name = actor.name
                except Exception:
                    identity_email = None

                # Fallback: decode bearer token directly if request context identity was not available.
                if not identity_email:
                    auth_header = request.headers.get("Authorization", "")
                    if auth_header.lower().startswith("bearer "):
                        raw_token = auth_header.split(" ", 1)[1].strip()
                        if raw_token:
                            try:
                                decoded = decode_token(raw_token)
                                sub = decoded.get("sub")
                                if isinstance(sub, dict):
                                    sub = sub.get("email")
                                if isinstance(sub, str) and sub.strip():
                                    identity_email = sub.strip().lower()
                                    actor = User.query.filter(func.lower(User.email) == identity_email).first()
                                    if actor:
                                        actor_id = actor.id
                                        actor_name = actor.name
                                elif isinstance(sub, int):
                                    actor = User.query.get(sub)
                                    if actor:
                                        identity_email = (actor.email or "").strip().lower() or None
                                        actor_id = actor.id
                                        actor_name = actor.name
                            except Exception:
                                pass

                # Login route has no JWT yet; resolve actor from payload email instead.
                if (not actor_name) and path == "/api/v1/login":
                    payload = request.get_json(silent=True) or {}
                    login_email = str(payload.get("email") or "").strip().lower()
                    if login_email:
                        login_actor = User.query.filter(func.lower(User.email) == login_email).first()
                        if login_actor:
                            actor_id = login_actor.id
                            actor_name = login_actor.name
                            identity_email = login_actor.email
                        else:
                            # Keep traceability for unknown login attempts
                            identity_email = login_email

                action = f"{request.method} {path}"
                success = response.status_code < 400
                create_audit_log(
                    action=action,
                    target_type=None,
                    target_id=None,
                    target_name=None,
                    description=f"{request.remote_addr or ''}".strip() or None,
                    old_value=None,
                    new_value={
                        "status_code": response.status_code,
                        "user": identity_email,
                    },
                    success=success,
                    error_message=None if success else getattr(response, "get_data", lambda **_: None)(as_text=True) if hasattr(response, "get_data") else None,
                    actor_user_id=actor_id,
                    actor_user_email=identity_email,
                    actor_user_name=actor_name,
                )
            except Exception:
                # Never break the request if audit logging fails
                pass
            return response
        
        # Register blueprints
        app.register_blueprint(user_v1)
        app.register_blueprint(batch_v1)
        app.register_blueprint(investment_v1)
        app.register_blueprint(fund_v1)
        app.register_blueprint(funds_v1)
        app.register_blueprint(performance_v1)
        app.register_blueprint(valuation_v1)
        app.register_blueprint(reports_v1)
        app.register_blueprint(stats_v1)
        app.register_blueprint(audit_v1)
        app.register_blueprint(backup_v1)
        app.register_blueprint(bulk_upload_v1)
        app.register_blueprint(settings_v1)

        # app.app_context().push() above (line ~50) is never popped — it stays
        # active for the whole process so ad-hoc db.session use outside a request
        # (scheduler startup, the migration/backfill statements above) has an app
        # context to resolve against. But that also means db.session itself is
        # never torn down by the normal per-request teardown_appcontext hook, so
        # any read done during startup (e.g. apply_email_settings_to_app's SELECT)
        # was left sitting as a permanent "idle in transaction" connection for the
        # life of the process — found live via pg_stat_activity, and exactly the
        # kind of held lock that can block a later ALTER TABLE/CREATE INDEX on
        # the next restart. Closing the session here (without popping the context
        # itself) returns that connection to the pool; every subsequent request
        # still gets its own fresh session via the normal per-request lifecycle.
        db.session.remove()

        return app

app = create_app(config_filename=Config)

if __name__ == "__main__":

    app.run(host='127.0.0.1', port=4455, debug=True)