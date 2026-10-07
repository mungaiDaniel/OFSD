import os
import sys
import traceback
from getpass import getpass

from werkzeug.security import generate_password_hash


def _prompt(label: str) -> str:
    val = input(f"{label}: ").strip()
    if not val:
        raise ValueError(f"{label} is required")
    return val


def main() -> int:
    # Ensure backend imports work when running as a script
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    # NOTE:
    # This script does NOT call any API endpoint.
    # It writes directly to PostgreSQL using SQLAlchemy.
    from flask import Flask  # noqa
    from sqlalchemy import text  # noqa
    from config import DevelopmentConfig  # noqa
    from app.database.database import db  # noqa
    from app.Admin.model import User  # noqa

    # If DATABASE_URI isn't set, prompt so we don't accidentally write to the wrong DB.
    if not os.environ.get("DATABASE_URI"):
        print("DATABASE_URI is not set.")
        print("Enter your PostgreSQL connection string to create the super admin in the correct database.")
        print("Example: postgresql://postgres:<PASSWORD>@localhost:5432/<DB_NAME>")
        os.environ["DATABASE_URI"] = _prompt("DATABASE_URI")

    app = Flask(__name__)
    app.config.from_object(DevelopmentConfig)
    # Explicit override so the prompted DATABASE_URI is never ignored
    if os.environ.get("DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URI"].strip()
    db.init_app(app)

    # Connect and migrate before asking for passwords (fail fast on bad URI / credentials)
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"))
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("ERROR: Database connection or migration step failed.")
            print(f"  Using URI: {app.config.get('SQLALCHEMY_DATABASE_URI', '(not set)')!s}")
            print(f"  Details: {e}")
            traceback.print_exc()
            return 1

    name = _prompt("Name")
    email = _prompt("Email").lower()
    password = getpass("Password: ").strip()
    confirm = getpass("Confirm Password: ").strip()
    if password != confirm:
        raise ValueError("Passwords do not match")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            print(f"User already exists: id={existing.id} email={existing.email}")
            return 0

        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            status="active",
            role="super_admin",
        )
        db.session.add(user)
        db.session.commit()
        print(f"Created super_admin: id={user.id} email={user.email} status={user.status}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise SystemExit(1)

