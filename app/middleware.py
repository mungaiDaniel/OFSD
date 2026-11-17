"""Request middleware: account gatekeeper and mutation audit trail."""
from flask import request, jsonify, make_response
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, decode_token
from datetime import datetime, timezone
from sqlalchemy import func
from app.Admin.model import User
from app.utils.audit_log import create_audit_log


def register_middleware(app) -> None:
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

