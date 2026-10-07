from flask import Blueprint, jsonify, make_response, current_app, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from app.database.database import db
from app.Backup.model import BackupLog
from app.utils.backup_service import BackupService
from app.logic.batch_scheduler_service import BatchSchedulerService


backup_v1 = Blueprint("backup_v1", __name__, url_prefix="/")


def _require_superadmin():
    claims = get_jwt() or {}
    if int(claims.get("admin", 0) or 0) != 2:
        return make_response(jsonify({"status": 403, "message": "Superadmin access required"}), 403)
    return None


@backup_v1.route("/api/v1/backups", methods=["GET"])
@jwt_required()
def list_backups():
    deny = _require_superadmin()
    if deny:
        return deny

    try:
        limit = min(max(request.args.get("limit", default=50, type=int) or 50, 1), 200)
        rows = (
            db.session.query(BackupLog)
            .order_by(BackupLog.started_at.desc())
            .limit(limit)
            .all()
        )
        return jsonify({"status": 200, "message": "Backups retrieved", "data": [r.to_dict() for r in rows]}), 200
    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@backup_v1.route("/api/v1/backups/status", methods=["GET"])
@jwt_required()
def backup_status():
    deny = _require_superadmin()
    if deny:
        return deny

    try:
        enabled = bool(current_app.config.get("DB_BACKUP_ENABLED"))
        next_run = None
        scheduler = BatchSchedulerService.scheduler
        if scheduler is not None:
            job = scheduler.get_job("daily_db_backup_task")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        last = db.session.query(BackupLog).order_by(BackupLog.started_at.desc()).first()

        return jsonify({
            "status": 200,
            "message": "Backup status retrieved",
            "data": {
                "enabled": enabled,
                "next_run_at": next_run,
                "last_backup": last.to_dict() if last else None,
            },
        }), 200
    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500


@backup_v1.route("/api/v1/backups/run-now", methods=["POST"])
@jwt_required()
def run_backup_now():
    deny = _require_superadmin()
    if deny:
        return deny

    try:
        identity = get_jwt_identity()
        user_email = identity if isinstance(identity, str) else (identity or {}).get("email")

        log = BackupService.run_database_backup(current_app._get_current_object(), triggered_by="manual", user_email=user_email)

        if log.status != "success":
            return jsonify({"status": 500, "message": log.error_message or "Backup failed", "data": log.to_dict()}), 500

        return jsonify({"status": 200, "message": "Backup completed", "data": log.to_dict()}), 200
    except Exception as e:
        return jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500
