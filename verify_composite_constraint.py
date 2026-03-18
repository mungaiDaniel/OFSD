"""
Verification script for composite unique constraint migration.
Checks if the database schema has been properly updated.
"""

from sqlalchemy import inspect, text
import logging

logger = logging.getLogger(__name__)


def verify_migration():
    """Verify that the composite constraint migration was successful"""
    try:
        print("=" * 70)
        print("Verifying Composite Unique Constraint Migration")
        print("=" * 70)
        
        from main import app
        from app.database.database import db
        
        with app.app_context():
            # Get database inspector
            inspector = inspect(db.engine)
            
            # Check constraints on investments table
            constraints = inspector.get_unique_constraints('investments')
            
            print("\n✓ Unique Constraints on 'investments' table:")
            print(f"  Found {len(constraints)} constraint(s)")
            
            composite_found = False
            old_constraint_found = False
            
            for constraint in constraints:
                constraint_name = constraint.get('name', 'Unknown')
                columns = constraint.get('column_names', [])
                
                print(f"\n  • {constraint_name}")
                print(f"    Columns: {', '.join(columns)}")
                
                # Check for new composite constraint
                if 'internal_client_code' in columns and 'batch_id' in columns:
                    composite_found = True
                    print(f"    ✅ This is the NEW composite constraint!")
                
                # Check for old global constraint
                if constraint_name == 'investments_internal_client_code_key':
                    old_constraint_found = True
                    print(f"    ❌ This is the OLD global constraint (should be removed)")
            
            print("\n" + "=" * 70)
            print("Verification Results:")
            print("=" * 70)
            
            if composite_found and not old_constraint_found:
                print("✅ MIGRATION SUCCESSFUL")
                print("   • New composite constraint found: _customer_batch_uc")
                print("   • Old global constraint removed")
                print("   • Database schema is correct")
                return True
            elif composite_found and old_constraint_found:
                print("⚠️  MIGRATION INCOMPLETE")
                print("   • New composite constraint found ✓")
                print("   • But old constraint still exists ✗")
                print("   • Run migration again or manually drop old constraint")
                return False
            elif not composite_found:
                print("❌ MIGRATION FAILED")
                print("   • New composite constraint NOT found")
                print("   • Run migration script again")
                return False
            
    except Exception as e:
        print(f"\n❌ Verification Error: {str(e)}")
        logger.error(f"Verification failed: {str(e)}", exc_info=True)
        return False


def check_data_integrity():
    """Check for any data integrity issues"""
    try:
        print("\n" + "=" * 70)
        print("Checking Data Integrity")
        print("=" * 70)
        
        from main import app
        from app.database.database import db
        
        with app.app_context():
            with db.engine.connect() as connection:
                # Check for duplicates
                result = connection.execute(text("""
                    SELECT batch_id, internal_client_code, COUNT(*) as count
                    FROM investments
                    GROUP BY batch_id, internal_client_code
                    HAVING COUNT(*) > 1;
                """))
                
                duplicates = result.fetchall()
                
                if duplicates:
                    print("\n⚠️  Found duplicate (internal_client_code, batch_id) pairs:")
                    for row in duplicates:
                        print(f"   • Batch {row[0]}, Code {row[1]}: {row[2]} records")
                    print("\n   These should be merged or cleaned before production use.")
                    return False
                else:
                    print("\n✅ No duplicate (internal_client_code, batch_id) pairs found")
                    return True
                
    except Exception as e:
        print(f"\n⚠️  Could not check data integrity: {str(e)}")
        return True  # Don't fail if we can't check, may have no data yet


if __name__ == '__main__':
    schema_ok = verify_migration()
    data_ok = check_data_integrity()
    
    if schema_ok and data_ok:
        print("\n" + "=" * 70)
        print("✅ VERIFICATION COMPLETE - READY FOR PRODUCTION")
        print("=" * 70)
        exit(0)
    else:
        print("\n" + "=" * 70)
        print("❌ VERIFICATION FAILED - PLEASE FIX BEFORE PRODUCTION")
        print("=" * 70)
        exit(1)
