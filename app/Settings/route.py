"""
Settings -> Email Sending / Email Queue.

Everything here is super_admin only — these are infrastructure credentials
and delivery-rate controls, not per-user preferences.
"""
import logging

from flask import Blueprint, jsonify, make_response, request, current_app
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from app.database.database import db
from app.Admin.route import _require_superadmin
from app.Settings.service import (
    get_effective_email_settings,
    save_email_settings,
    save_email_queue_settings,
)

logger = logging.getLogger(__name__)

settings_v1 = Blueprint("settings_v1", __name__, url_prefix="/")


@settings_v1.route("/api/v1/settings/email", methods=["GET"])
@jwt_required()
def get_email_settings():
    deny = _require_superadmin()
    if deny:
        return deny
    try:
        effective = get_effective_email_settings(current_app, db.session)
        return make_response(jsonify({"status": 200, "data": effective}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@settings_v1.route("/api/v1/settings/email", methods=["PATCH"])
@jwt_required()
def patch_email_settings():
    deny = _require_superadmin()
    if deny:
        return deny
    try:
        data = request.get_json(silent=True) or {}

        if "mail_port" in data and data["mail_port"] is not None:
            try:
                port = int(data["mail_port"])
            except (TypeError, ValueError):
                return make_response(jsonify({"status": 400, "message": "mail_port must be a number"}), 400)
            if port < 1 or port > 65535:
                return make_response(jsonify({"status": 400, "message": "mail_port must be between 1 and 65535"}), 400)

        updated_by = get_jwt().get("sub") or get_jwt_identity()
        save_email_settings(current_app, db.session, data, updated_by=str(updated_by) if updated_by else None)

        effective = get_effective_email_settings(current_app, db.session)
        return make_response(jsonify({
            "status": 200,
            "message": "Email settings saved and applied.",
            "data": effective,
        }), 200)
    except Exception as e:
        logger.error(f"Failed to save email settings: {e}", exc_info=True)
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@settings_v1.route("/api/v1/settings/email/test", methods=["POST"])
@jwt_required()
def send_test_email():
    """Sends a real test email using whatever settings are CURRENTLY saved/applied
    — the one place an admin can confirm new SMTP credentials actually work
    before trusting them for real investor emails. Bypasses the pending-email
    approval queue entirely (a test email is not investor-facing) but still
    respects MAIL_SUPPRESS_SEND, so it's a no-op (reports success without
    sending) when suppression is on."""
    deny = _require_superadmin()
    if deny:
        return deny
    try:
        data = request.get_json(silent=True) or {}
        recipient = (data.get("recipient") or "").strip()
        if not recipient:
            return make_response(jsonify({"status": 400, "message": "recipient is required"}), 400)

        from app.utils.email_service import EmailService, mail
        from flask_mail import Message

        subject = "OFDS test email"
        body = (
            "This is a test email sent from OFDS Settings -> Email Sending.\n\n"
            f"Sent by: {get_jwt().get('sub') or get_jwt_identity()}\n"
            "If you received this, your SMTP settings are working."
        )
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body,
            html=EmailService._render_html_body(body),
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        )
        mail.send(msg)
        suppressed = bool(current_app.config.get("MAIL_SUPPRESS_SEND"))
        return make_response(jsonify({
            "status": 200,
            "message": (
                "MAIL_SUPPRESS_SEND is on — nothing was actually sent, but the settings/credentials are valid."
                if suppressed else f"Test email sent to {recipient}."
            ),
            "data": {"suppressed": suppressed},
        }), 200)
    except Exception as e:
        logger.error(f"Test email failed: {e}", exc_info=True)
        return make_response(jsonify({"status": 500, "message": f"Send failed: {str(e)}"}), 500)


@settings_v1.route("/api/v1/settings/email-queue", methods=["GET"])
@jwt_required()
def get_email_queue_settings():
    deny = _require_superadmin()
    if deny:
        return deny
    try:
        from app.logic.email_queue_scheduler_service import EmailQueueSchedulerService
        effective = get_effective_email_settings(current_app, db.session)
        status = EmailQueueSchedulerService.get_status()
        return make_response(jsonify({
            "status": 200,
            "data": {
                "batch_size": effective.get("email_queue_batch_size"),
                "interval_minutes": effective.get("email_queue_interval_minutes"),
                "next_run_at": status.get("next_run_at"),
                "queued_count": status.get("queued_count"),
            },
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@settings_v1.route("/api/v1/settings/email-queue", methods=["PATCH"])
@jwt_required()
def patch_email_queue_settings():
    deny = _require_superadmin()
    if deny:
        return deny
    try:
        data = request.get_json(silent=True) or {}
        try:
            batch_size = int(data.get("batch_size"))
            interval_minutes = int(data.get("interval_minutes"))
        except (TypeError, ValueError):
            return make_response(jsonify({"status": 400, "message": "batch_size and interval_minutes are required numbers"}), 400)

        if batch_size < 1 or batch_size > 1000:
            return make_response(jsonify({"status": 400, "message": "batch_size must be between 1 and 1000"}), 400)
        if interval_minutes < 1 or interval_minutes > 1440:
            return make_response(jsonify({"status": 400, "message": "interval_minutes must be between 1 and 1440"}), 400)

        updated_by = get_jwt().get("sub") or get_jwt_identity()
        save_email_queue_settings(current_app, db.session, batch_size, interval_minutes, updated_by=str(updated_by) if updated_by else None)

        return make_response(jsonify({
            "status": 200,
            "message": f"Email queue updated: up to {batch_size} emails every {interval_minutes} minute(s).",
        }), 200)
    except Exception as e:
        logger.error(f"Failed to save email queue settings: {e}", exc_info=True)
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)
