import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from app.database.database import db

import main

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
VERSIONS_DIR = BASE_DIR / "migrations" / "versions"


def load_migration_module(path: Path):
    spec = spec_from_file_location(path.stem, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_schema_migration(connection, module):
    if not hasattr(module, "upgrade"):
        return
    print(f"Applying schema migration: {module.__name__}")
    migration_context = MigrationContext.configure(connection=connection)
    with Operations.context(migration_context):
        module.upgrade()
    print(f"Completed schema migration: {module.__name__}\n")


def run_manual_migration(module):
    if not hasattr(module, "run_migration"):
        return
    print(f"Running manual migration: {module.__name__}")
    module.run_migration(db.session)
    print(f"Completed manual migration: {module.__name__}\n")


def run_migrations():
    print("Starting migration runner...")
    print(f"Using database URI: {main.app.config.get('SQLALCHEMY_DATABASE_URI')}\n")

    schema_files = []
    manual_files = []

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        module = load_migration_module(path)
        if hasattr(module, "revision") and hasattr(module, "upgrade"):
            schema_files.append((path.name, module))
        elif hasattr(module, "run_migration"):
            manual_files.append((path.name, module))

    if not schema_files and not manual_files:
        print("No migration scripts found.")
        return

    engine = db.engine
    for filename, module in schema_files:
        print(f"=== Executing schema file: {filename} ===")
        with engine.connect() as connection:
            with connection.begin():
                try:
                    run_schema_migration(connection, module)
                except Exception as exc:
                    print(f"WARNING: schema migration {filename} failed: {exc}")
                    print("Rolling back and continuing with next migration.\n")

    if manual_files:
        print("Running standalone/manual migrations...\n")
        for filename, module in manual_files:
            print(f"=== Executing manual file: {filename} ===")
            try:
                run_manual_migration(module)
            except Exception as exc:
                print(f"WARNING: manual migration {filename} failed: {exc}")
                print("Rolling back session and continuing.\n")
                db.session.rollback()

    print("Migration runner complete.")


if __name__ == "__main__":
    run_migrations()
