"""
Database Migration: Replace global unique constraint with composite constraint.

This migration allows one internal_client_code to appear in multiple batches,
but not twice in the same batch.

Changes:
1. Drop the existing global unique constraint on internal_client_code
2. Add new composite unique constraint on (internal_client_code, batch_id)
"""

from app.database.database import db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Execute the migration"""
    try:
        print("=" * 70)
        print("Starting database migration: Composite Unique Constraint")
        print("=" * 70)
        
        migrations = [
            {
                'name': 'Drop existing unique constraint',
                'sql': 'ALTER TABLE investments DROP CONSTRAINT IF EXISTS investments_internal_client_code_key;',
                'description': 'Remove the global unique constraint on internal_client_code'
            },
            {
                'name': 'Add composite unique constraint',
                'sql': 'ALTER TABLE investments ADD CONSTRAINT _customer_batch_uc UNIQUE (internal_client_code, batch_id);',
                'description': 'Add composite constraint: (internal_client_code, batch_id) must be unique within the table'
            },
        ]
        
        with db.engine.connect() as connection:
            for step_num, migration in enumerate(migrations, 1):
                try:
                    print(f"\n[Step {step_num}/{len(migrations)}] {migration['name']}")
                    print(f"Description: {migration['description']}")
                    print(f"SQL: {migration['sql']}")
                    
                    # Execute the migration
                    connection.execute(text(migration['sql']))
                    connection.commit()
                    
                    print(f"✅ {migration['name']} - SUCCESS")
                    
                except Exception as e:
                    if "does not exist" in str(e) or "already exists" in str(e):
                        # These are acceptable - the constraint may already be dropped/added
                        print(f"⚠️  {migration['name']} - SKIPPED (Already applied or doesn't exist)")
                    else:
                        raise
        
        print("\n" + "=" * 70)
        print("✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\nSummary of changes:")
        print("  • Removed global unique constraint on internal_client_code")
        print("  • Added composite unique constraint on (internal_client_code, batch_id)")
        print("  • Same investor can now exist in multiple batches")
        print("  • Each investor can only appear once per batch")
        return True
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {str(e)}")
        print("=" * 70)
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        return False


if __name__ == '__main__':
    # Flask app context required for db.engine access
    from main import app
    
    with app.app_context():
        success = run_migration()
        exit(0 if success else 1)
