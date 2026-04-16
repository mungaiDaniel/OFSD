import os
import sys
import importlib
import traceback
from getpass import getpass
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

def _prompt(label: str, default: str = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    if not val and not default:
        raise ValueError(f"{label} is required")
    return val or default

def main() -> int:
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from config import DevelopmentConfig
    from app.database.database import db
    from app.Admin.model import User

    print("=== Table Reset & Superadmin Setup ===")
    
    # 1. Get Database URI (required input, no default)
    print("\nWARNING: This operation is DESTRUCTIVE.")
    print("It will DROP and RECREATE all tables in the target database.")
    db_uri = _prompt("Target Database URI")

    # Parse DB Name for confirmation prompt
    try:
        _, db_name = db_uri.rsplit("/", 1)
        if "?" in db_name:  # Handle query params if any
            db_name = db_name.split("?")[0]
    except ValueError:
        print("ERROR: Invalid Database URI format.")
        return 1

    typed = input(f'\nType "RESET TABLES {db_name.upper()}" to confirm: ').strip()
    if typed != f"RESET TABLES {db_name.upper()}":
        print("Cancelled. No changes made.")
        return 1

    # 2. Initialize app and schema metadata
    print("\nInitializing app and schema metadata...")
    app = Flask(__name__)
    app.config.from_object(DevelopmentConfig)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    db.init_app(app)

    # Import models to register metadata
    model_modules = [
        "app.Admin.model",
        "app.Batch.core_fund",
        "app.Batch.fund",
        "app.Batch.model",
        "app.Investments.model",
        "app.Performance.model",
        "app.Valuation.model",
        "app.utils.audit_log",
    ]
    for module_name in model_modules:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            print(f"Warning: Could not import {module_name}: {e}")

    # 3. Hard reset tables at schema level (PostgreSQL)
    print(f"\nDropping and recreating all tables in '{db_name}'...")
    try:
        with app.app_context():
            # Best-effort: terminate other sessions in a separate AUTOCOMMIT connection.
            # If this fails due to privileges, it must not affect the reset transaction.
            try:
                with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    conn.execute(
                        text(
                            """
                            SELECT pg_terminate_backend(pid)
                            FROM pg_stat_activity
                            WHERE datname = current_database()
                              AND pid <> pg_backend_pid();
                            """
                        )
                    )
            except SQLAlchemyError as terminate_err:
                print(f"Warning: could not terminate other DB sessions: {terminate_err}")

            # db.drop_all() only drops tables known to SQLAlchemy metadata.
            # This schema reset removes ALL existing tables (including unknown/legacy ones).
            with db.engine.begin() as conn:
                # Avoid hanging forever if another session holds locks.
                conn.execute(text("SET lock_timeout = '10s'"))
                conn.execute(text("SET statement_timeout = '60s'"))

                conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
            db.create_all()
            db.session.commit()
        print("Tables reset and schema initialized.")
    except Exception as e:
        print(f"ERROR resetting tables: {e}")
        return 1

    # 4. Create Super Admin
    print("\n=== Create Super Admin User ===")
    name = _prompt("Admin Name", "Super User")
    email = _prompt("Admin Email", "admin@offshore.com").lower()
    password = getpass("Admin Password (min 8 chars): ").strip()
    if len(password) < 8:
        print("ERROR: Password too short.")
        return 1
    
    confirm = getpass("Confirm Password: ").strip()
    if password != confirm:
        print("ERROR: Passwords do not match.")
        return 1

    with app.app_context():
        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            status="active",
            role="super_admin",
        )
        db.session.add(user)
        db.session.commit()
        print(f"\nSuper Admin '{email}' created successfully.")

    print("\nDONE: Table reset and setup complete.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
