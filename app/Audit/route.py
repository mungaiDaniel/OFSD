import csv
from io import StringIO
from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required, get_jwt
from sqlalchemy import func
from app.utils.audit_log import AuditLog
from app.database.database import db
from app.Admin.model import User


audit_v1 = Blueprint("audit_v1", __name__, url_prefix="/")


def _require_superadmin():
    claims = get_jwt() or {}
    if int(claims.get("admin", 0) or 0) != 2:
        return make_response(jsonify({"status": 403, "message": "Superadmin access required"}), 403)
    return None


@audit_v1.route("/api/v1/audit-logs", methods=["GET"])
@jwt_required()
def get_audit_logs():
    deny = _require_superadmin()
    if deny:
        return deny

    action = request.args.get("action")
    target_type = request.args.get("target_type")
    try:
        page = int(request.args.get("page") or 1)
        per_page = int(request.args.get("per_page") or 50)
    except Exception:
        return make_response(jsonify({"status": 400, "message": "page and per_page must be integers"}), 400)

    page = max(page, 1)
    per_page = min(max(per_page, 1), 200)

    q = db.session.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)

    items = q.limit(per_page).offset((page - 1) * per_page).all()
    data = []
    for i in items:
        d = i.to_dict()
        # Resolve missing names for older logs where actor details weren't saved
        if not d.get("user_name"):
            u = None
            if d.get("user_id"):
                u = User.query.get(d["user_id"])
            elif d.get("user_email"):
                u = User.query.filter(func.lower(User.email) == str(d["user_email"]).lower()).first()
            if u:
                d["user_name"] = u.name
                d["user_email"] = u.email
        # Keep UI clean: always provide a human label, never raw "system"
        if not d.get("user_name"):
            if d.get("user_email"):
                d["user_name"] = str(d["user_email"]).split("@")[0]
            else:
                d["user_name"] = "Unknown user"
        data.append(d)
    return make_response(jsonify({"status": 200, "data": data}), 200)


@audit_v1.route("/api/v1/audit-logs/export", methods=["GET"])
@jwt_required()
def export_audit_logs():
    deny = _require_superadmin()
    if deny:
        return deny

    action = request.args.get("action")
    target_type = request.args.get("target_type")

    q = db.session.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    rows = q.limit(5000).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "action", "target_type", "target_id", "target_name",
        "user_id", "user_name", "user_email", "description",
        "status", "ip_address", "user_agent", "error_message"
    ])
    for r in rows:
        writer.writerow([
            r.timestamp.isoformat() if r.timestamp else "",
            r.action or "",
            r.target_type or "",
            r.target_id or "",
            r.target_name or "",
            r.user_id or "",
            r.user_name or "",
            r.user_email or "",
            r.description or "",
            "OK" if r.success else "FAIL",
            r.ip_address or "",
            r.user_agent or "",
            r.error_message or "",
        ])

    csv_data = output.getvalue()
    response = make_response(csv_data, 200)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=audit_logs.csv"
    return response

