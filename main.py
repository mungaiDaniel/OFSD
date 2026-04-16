from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from config import DevelopmentConfig as Config
from app.database.database import db
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt_identity, decode_token
from datetime import timedelta
from app.Admin.route import user_v1
from app.Batch.route import batch_v1
from app.Batch.fund_routes import fund_v1
from app.Investments.route import investment_v1
from app.Performance.route import performance_v1
from app.Valuation.route import valuation_v1
from app.Reports.route import reports_v1
from app.Stats.route import stats_v1
from app.Audit.route import audit_v1
from app.utils.email_service import EmailService
from sqlalchemy import text, func
from app.Admin.model import User
from app.utils.audit_log import AuditLog, create_audit_log



def create_app(config_filename):
        app = Flask(__name__)
        app.config.from_object(config_filename)
        app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
        app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=1)
        jwt = JWTManager(app)
        # Explicitly allow frontend origin to fix "Origin not allowed" when supports_credentials is True
        CORS(app, supports_credentials=True, resources={r"/*": {"origins": [
            "http://localhost:5173", 
            "http://127.0.0.1:5173",
            "https://osfmr2.aib-axysafrica.com"
        ]}})
        db.init_app(app)
        EmailService.init_app(app)
        app.app_context().push()
        db.create_all()
        db.session.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
        db.session.execute(text("ALTER TABLE pending_emails ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(120)"))
        db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_email VARCHAR(120)"))
        db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_name VARCHAR(120)"))
        # Add new columns for transfer transaction costs
        db.session.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS transfer_transaction_cost NUMERIC(20, 2) DEFAULT 0.00"))
        db.session.execute(text("ALTER TABLE investments ADD COLUMN IF NOT EXISTS transfer_fee_deducted NUMERIC(20, 2) DEFAULT 0.00"))
        # Gatekeeper user fields (safe, idempotent)
        db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"))
        db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'"))
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
        except Exception:
            # If legacy column doesn't exist, ignore.
            pass
        db.session.commit()

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
        app.register_blueprint(performance_v1)
        app.register_blueprint(valuation_v1)
        app.register_blueprint(reports_v1)
        app.register_blueprint(stats_v1)
        app.register_blueprint(audit_v1)
        
        return app

app = create_app(config_filename=Config)

if __name__ == "__main__":

    app.run(host='127.0.0.1', port=4455, debug=True)