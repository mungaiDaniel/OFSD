#!/usr/bin/env python3
"""
Comprehensive security test for fund management endpoints.
Verifies that ONLY super_admin users can create, edit, and delete funds.
"""

import os, sys, time
os.environ.setdefault("WERKZEUG_RUN_MAIN", "true")

from decimal import Decimal
from datetime import datetime, timezone
from main import app
from app.database.database import db
from app.Admin.model import User
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass

TAG = "ZZFUNDSEC"

def test_fund_security():
    """Test fund management security controls."""
    with app.app_context():
        session = db.session
        try:
            # 1. Create test users: super_admin and regular user
            print("\n=== Creating test users ===")
            super_admin = User(
                name="Super Admin",
                email="superadmin@test.com",
                password="hashed_pwd",
                role="super_admin",
                status="active"
            )
            regular_user = User(
                name="Regular User",
                email="regular@test.com",
                password="hashed_pwd",
                role="user",
                status="active"
            )
            session.add_all([super_admin, regular_user])
            session.commit()
            print(f"[OK] Created super_admin (id={super_admin.id}) and regular_user (id={regular_user.id})")

            # 2. Create test fund
            print("\n=== Creating test fund ===")
            test_fund = CoreFund(fund_name=f"{TAG}_Fund", fund_code="TEST", is_active=True)
            session.add(test_fund)
            session.commit()
            print(f"[OK] Created fund (id={test_fund.id})")

            # 3. Test authentication
            from flask_jwt_extended import create_access_token
            with app.test_client() as client:
                super_admin_token = create_access_token(identity=super_admin.id)
                regular_user_token = create_access_token(identity=regular_user.id)

                print("\n=== Testing CREATE fund endpoint ===")

                # Regular user should be DENIED
                print("Test 1: Regular user trying to CREATE fund...")
                r = client.post(
                    "/api/v1/funds",
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                    json={"fund_name": "Should Fail", "fund_code": "FAIL"}
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.json()}"
                assert "Super admin access required" in r.json()["message"]
                print(f"[OK] Regular user correctly DENIED: {r.json()['message']}")

                # Super admin should be ALLOWED
                print("Test 2: Super admin CREATE fund...")
                r = client.post(
                    "/api/v1/funds",
                    headers={"Authorization": f"Bearer {super_admin_token}"},
                    json={"fund_name": f"{TAG}_NewFund", "fund_code": "NEW"}
                )
                assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.json()}"
                new_fund = r.json()["data"]
                print(f"[OK] Super admin successfully created fund (id={new_fund['id']})")

                print("\n=== Testing PATCH (edit) fund endpoint ===")

                # Regular user should be DENIED
                print("Test 3: Regular user trying to PATCH fund...")
                r = client.patch(
                    f"/api/v1/funds/{new_fund['id']}",
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                    json={"fund_name": "Should Fail"}
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}"
                print(f"[OK] Regular user correctly DENIED")

                # Super admin should be ALLOWED
                print("Test 4: Super admin PATCH fund...")
                r = client.patch(
                    f"/api/v1/funds/{new_fund['id']}",
                    headers={"Authorization": f"Bearer {super_admin_token}"},
                    json={"fund_name": f"{TAG}_UpdatedFund"}
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
                assert r.json()["data"]["fund_name"] == f"{TAG}_UpdatedFund"
                print(f"[OK] Super admin successfully updated fund name")

                print("\n=== Testing DELETE fund endpoint ===")

                # Regular user should be DENIED
                print("Test 5: Regular user trying to DELETE fund...")
                r = client.delete(
                    f"/api/v1/funds/{new_fund['id']}",
                    headers={"Authorization": f"Bearer {regular_user_token}"}
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}"
                print(f"[OK] Regular user correctly DENIED")

                # Super admin should be ALLOWED
                print("Test 6: Super admin DELETE fund...")
                r = client.delete(
                    f"/api/v1/funds/{new_fund['id']}",
                    headers={"Authorization": f"Bearer {super_admin_token}"}
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
                print(f"[OK] Super admin successfully deleted (deactivated) fund")

                print("\n=== Testing ADD SHARE CLASS endpoint ===")

                # Regular user should be DENIED
                print("Test 7: Regular user trying to ADD share class...")
                r = client.post(
                    f"/api/v1/funds/{test_fund.id}/classes",
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                    json={"class_name": "Should Fail", "class_code": "FAIL", "currency": "KES"}
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}"
                print(f"[OK] Regular user correctly DENIED")

                # Super admin should be ALLOWED
                print("Test 8: Super admin ADD share class...")
                r = client.post(
                    f"/api/v1/funds/{test_fund.id}/classes",
                    headers={"Authorization": f"Bearer {super_admin_token}"},
                    json={"class_name": f"{TAG}_Class", "class_code": "TST", "currency": "KES"}
                )
                assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.json()}"
                share_class = r.json()["data"]
                print(f"[OK] Super admin successfully created share class (id={share_class['id']})")

                print("\n=== Testing UPDATE SHARE CLASS endpoint ===")

                # Regular user should be DENIED
                print("Test 9: Regular user trying to UPDATE share class...")
                r = client.patch(
                    f"/api/v1/funds/{test_fund.id}/classes/{share_class['id']}",
                    headers={"Authorization": f"Bearer {regular_user_token}"},
                    json={"class_name": "Should Fail"}
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}"
                print(f"[OK] Regular user correctly DENIED")

                # Super admin should be ALLOWED
                print("Test 10: Super admin UPDATE share class...")
                r = client.patch(
                    f"/api/v1/funds/{test_fund.id}/classes/{share_class['id']}",
                    headers={"Authorization": f"Bearer {super_admin_token}"},
                    json={"class_name": f"{TAG}_UpdatedClass"}
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
                print(f"[OK] Super admin successfully updated share class")

            print("\nSUCCESS: ALL SECURITY TESTS PASSED!")
            return True

        except AssertionError as e:
            print(f"\nFAIL: TEST FAILED: {str(e)}")
            return False
        except Exception as e:
            print(f"\nFAIL: ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Cleanup
            session.rollback()
            session.query(User).filter(User.email.in_([f"superadmin@test.com", "regular@test.com"])).delete(synchronize_session=False)
            session.query(ShareClass).filter(ShareClass.class_name.like(f"{TAG}%")).delete(synchronize_session=False)
            session.query(CoreFund).filter(CoreFund.fund_name.like(f"{TAG}%")).delete(synchronize_session=False)
            session.commit()
            session.remove()
            db.engine.dispose()


if __name__ == "__main__":
    success = test_fund_security()
    sys.exit(0 if success else 1)
