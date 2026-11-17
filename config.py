"""Application configuration.

Everything environment-specific is read from environment variables (a local
``.env`` file is loaded automatically). See ``.env.example`` for the full list.
No secrets live in this file: ``SECRET_KEY`` is mandatory outside of
development/testing, and mail/Azure credentials default to ``None``.
"""
import os
from datetime import timedelta
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


class BaseConfig:
    """Settings shared by every environment."""

    DEBUG = False
    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Auth -------------------------------------------------------------
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int("JWT_ACCESS_MINUTES", 60))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int("JWT_REFRESH_DAYS", 7))
    # Tokens are only accepted from the Authorization header. Query-string
    # tokens leak into server logs and browser history.
    JWT_TOKEN_LOCATION = ["headers"]

    # --- CORS -------------------------------------------------------------
    CORS_ORIGINS = _list(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    )

    # --- Email (SMTP) -----------------------------------------------------
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.office365.com")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
    MAIL_BCC = os.environ.get("MAIL_BCC")
    # Never dump the raw SMTP conversation (incl. attachments) unless asked.
    MAIL_DEBUG = _bool("MAIL_DEBUG", False)
    # Safe by default: nothing is really sent unless explicitly enabled.
    MAIL_SUPPRESS_SEND = _bool("MAIL_SUPPRESS_SEND", True)
    MANUAL_EMAIL_APPROVAL = _bool("MANUAL_EMAIL_APPROVAL", True)

    # Confirm only marks an email "Queued"; a background job drains the queue
    # at this rate to stay under provider throttling limits.
    EMAIL_QUEUE_INTERVAL_MINUTES = _int("EMAIL_QUEUE_INTERVAL_MINUTES", 5)
    EMAIL_QUEUE_BATCH_SIZE = _int("EMAIL_QUEUE_BATCH_SIZE", 100)

    # --- Daily database backups (pg_dump -> OneDrive); opt-in ---------------
    DB_BACKUP_ENABLED = _bool("DB_BACKUP_ENABLED", False)
    DB_BACKUP_HOUR_UTC = _int("DB_BACKUP_HOUR_UTC", 1)
    DB_BACKUP_MINUTE_UTC = _int("DB_BACKUP_MINUTE_UTC", 0)
    PG_DUMP_PATH = os.environ.get("PG_DUMP_PATH") or "pg_dump"
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    ONEDRIVE_USER_ID = os.environ.get("ONEDRIVE_USER_ID")
    ONEDRIVE_BACKUP_FOLDER = os.environ.get("ONEDRIVE_BACKUP_FOLDER") or "OFSD-DB-Backups"

    # Minimum deposit (before fees) accepted into a SHARES batch.
    MIN_DEPOSIT_USD = Decimal(os.environ.get("MIN_DEPOSIT_USD", "2000"))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-key-do-not-use-in-production-0000"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URI", "postgresql://postgres:postgres@localhost:5432/ofsd"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing-only-insecure-key-minimum-32-bytes-long-0000"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URI", "postgresql://postgres:postgres@localhost:5432/ofsd_test"
    )
    MAIL_SUPPRESS_SEND = True  # tests must never reach a real SMTP server


class ProductionConfig(BaseConfig):
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI")
    MAIL_SUPPRESS_SEND = _bool("MAIL_SUPPRESS_SEND", False)

    @classmethod
    def validate(cls) -> None:
        missing = [n for n in ("SECRET_KEY", "DATABASE_URI") if not os.environ.get(n)]
        if missing:
            raise RuntimeError(
                "Missing required environment variables for production: " + ", ".join(missing)
            )
        if len(cls.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters long")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    """Return the config class for ``name`` (default: ``$APP_ENV`` or development)."""
    name = (name or os.environ.get("APP_ENV") or "development").lower()
    try:
        cfg = CONFIGS[name]
    except KeyError:
        raise RuntimeError(f"Unknown APP_ENV {name!r}; expected one of {sorted(CONFIGS)}") from None
    if hasattr(cfg, "validate"):
        cfg.validate()
    return cfg
