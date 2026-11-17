"""Application factory and entry point.

Run locally with ``python main.py`` or in production with
``gunicorn main:app`` (see ``Procfile`` / ``Dockerfile``).
"""
import logging
import os
import sys

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from app.Admin.route import user_v1
from app.Audit.route import audit_v1
from app.Backup.route import backup_v1
from app.Batch.fund_routes import fund_v1
from app.Batch.route import batch_v1
from app.BulkUpload.route import bulk_upload_v1
from app.Funds.routes import funds_v1
from app.Investments.route import investment_v1
from app.Performance.route import performance_v1
from app.Reports.route import reports_v1
from app.Settings.route import settings_v1
from app.Stats.route import stats_v1
from app.Valuation.route import valuation_v1
from app.database.database import db
from app.database.schema_sync import sync_schema
from app.middleware import register_middleware
from app.startup import start_background_services
from app.utils.email_service import EmailService
from config import get_config

log = logging.getLogger(__name__)

BLUEPRINTS = (
    user_v1, batch_v1, investment_v1, fund_v1, funds_v1, performance_v1, valuation_v1,
    reports_v1, stats_v1, audit_v1, backup_v1, bulk_upload_v1, settings_v1,
)


def _register_error_handlers(app: Flask) -> None:
    """Return JSON (never HTML) for errors, with accurate status codes."""

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        return jsonify({"status": err.code, "message": err.description}), err.code

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        log.exception("Unhandled error")
        return jsonify({"status": 500, "message": "Internal server error"}), 500

    @app.get("/api/v1/health")
    def _health():
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok"})


def _is_reloader_parent(app: Flask) -> bool:
    """True in the Werkzeug reloader's watcher process.

    The debug reloader imports this module twice (watcher + worker). Schedulers
    and schema sync must only run in the worker, otherwise two schedulers send
    the same queued email twice and concurrent DDL can deadlock Postgres.
    Gunicorn never sets WERKZEUG_RUN_MAIN, hence the explicit exclusion.
    """
    return (
        app.debug
        and "gunicorn" not in sys.modules
        and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    )


def create_app(config=None) -> Flask:
    """Build the Flask app. ``config`` is a config class (default: ``$APP_ENV``)."""
    app = Flask(__name__)
    app.config.from_object(config or get_config())

    JWTManager(app)
    CORS(
        app,
        supports_credentials=True,
        resources={r"/*": {
            "origins": app.config["CORS_ORIGINS"],
            "expose_headers": ["Content-Disposition"],
        }},
    )
    db.init_app(app)
    Migrate(app, db)
    EmailService.init_app(app)

    # The context is kept open for ad-hoc db access during startup and by the
    # background schedulers; the session is released at the end of this function.
    app.app_context().push()
    db.create_all()

    try:
        from app.Settings.service import apply_email_settings_to_app
        apply_email_settings_to_app(app, db.session)
    except Exception:
        log.warning("Saved email settings not applied; using environment values", exc_info=True)

    if not _is_reloader_parent(app):
        sync_schema(db)
        start_background_services(app)

    register_middleware(app)
    _register_error_handlers(app)
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    # Return the startup connection to the pool so it doesn't linger as
    # "idle in transaction" and block later DDL.
    db.session.remove()
    return app


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 4455)), debug=app.debug)
