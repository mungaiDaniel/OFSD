import os
import sys
import importlib
import traceback
from getpass import getpass
from sqlalchemy import create_engine, text
from flask import Flask
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

    print("=== Database Reset & Superadmin Setup ===")
    
    # 1. Get Database URI
    default_uri = os.environ.get("DATABASE_URI", "postgresql://postgres:username@localhost:5432/offshore")
    print("\nWARNING: This operation is DESTRUCTIVE.")
    print("It will DROP and RECREATE the database itself.")
    db_uri = _prompt("Target Database URI", default_uri)

    # Parse DB Name and Admin URI
    try:
        base_uri, db_name = db_uri.rsplit("/", 1)
        if '?' in db_name: # Handle query params if any
            db_name = db_name.split('?')[0]
        admin_uri = f"{base_uri}/postgres"
    except ValueError:
        print("ERROR: Invalid Database URI format.")
        return 1

    typed = input(f'\nType "RESET {db_name.upper()}" to confirm deletion: ').strip()
    if typed != f"RESET {db_name.upper()}":
        print("Cancelled. No changes made.")
        return 1

    # 2. Recreate Database
    print(f"\nClosing connections and recreating database '{db_name}'...")
    try:
        admin_engine = create_engine(admin_uri, isolation_level='AUTOCOMMIT')
        with admin_engine.connect() as conn:
            # Terminate other connections to the target DB
            conn.execute(text(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{db_name}'
                AND pid <> pg_backend_pid();
            """))
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        print(f"Database '{db_name}' recreated successfully.")
    except Exception as e:
        print(f"ERROR recreating database: {e}")
        return 1

    # 3. Initialize Schema
    print("\nInitializing database schema...")
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

    with app.app_context():
        db.create_all()
        db.session.commit()
    print("Schema initialized.")

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

    print("\nDONE: Database reset and setup complete.")
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
