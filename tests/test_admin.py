"""
Admin & User Authentication Tests
==================================
Tests for user creation, authentication, and role management endpoints.

Run with: pytest tests/test_admin.py -v
"""

import pytest
import json
from datetime import datetime
from app.database.database import db
from app.Admin.model import User


def get_auth_headers(token):
    """Helper to create authorization headers"""
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.unit
class TestUserCreation:
    """Test creating new users"""
    
    def test_create_user_success(self, client):
        """Test successfully creating a new user"""
        payload = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'password': 'SecurePassword123!',
            'user_role': 'user'
        }
        
        response = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        data = response.get_json()
        # Handle both wrapped and direct response formats
        user_data = data.get('data', data) if isinstance(data, dict) and 'data' in data else data
        assert user_data.get('email') == 'john@example.com'
        assert user_data.get('user_role') == 'user'
    
    def test_create_user_missing_email(self, client):
        """Test validation: email is required"""
        payload = {
            'name': 'John Doe',
            'password': 'SecurePassword123!',
            'user_role': 'user'
        }
        
        response = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_user_missing_password(self, client):
        """Test validation: password is required"""
        payload = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'user_role': 'user'
        }
        
        response = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_create_user_duplicate_email(self, client):
        """Test validation: email must be unique"""
        payload = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'password': 'SecurePassword123!',
            'user_role': 'user'
        }
        
        # Create first user
        response1 = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        assert response1.status_code == 201
        
        # Try to create duplicate
        response2 = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        assert response2.status_code >= 400
    
    def test_create_admin_user(self, client):
        """Test creating an admin user"""
        payload = {
            'name': 'Admin User',
            'email': 'admin@example.com',
            'password': 'AdminPassword123!',
            'user_role': 'admin'
        }
        
        response = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        user = User.query.filter_by(email='admin@example.com').first()
        assert user.user_role == 'admin'
    
    def test_create_super_admin_user(self, client):
        """Test creating a super admin user"""
        payload = {
            'name': 'Super Admin',
            'email': 'superadmin@example.com',
            'password': 'SuperAdminPassword123!',
            'user_role': 'super_admin'
        }
        
        response = client.post(
            '/api/v1/users',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        user = User.query.filter_by(email='superadmin@example.com').first()
        assert user.user_role == 'super_admin'


@pytest.mark.unit
class TestUserLogin:
    """Test user authentication and login"""
    
    def test_login_success(self, client, app):
        """Test successful login with correct credentials"""
        # First create a user
        payload = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'password': 'SecurePassword123!'
        }
        
        with app.app_context():
            user = User(
                name='John Doe',
                email='john@example.com',
                password=User.generate_password_hash('SecurePassword123!'),
                user_role='user'
            )
            db.session.add(user)
            db.session.commit()
        
        # Now login
        login_payload = {
            'email': 'john@example.com',
            'password': 'SecurePassword123!'
        }
        
        response = client.post(
            '/api/v1/login',
            data=json.dumps(login_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'access_token' in data['value']
        assert 'refresh_token' in data['value']
        assert data['value']['user_role'] == 'user'
        assert data['value']['name'] == 'John Doe'
    
    def test_login_wrong_password(self, client, app):
        """Test login with incorrect password"""
        # Create a user
        with app.app_context():
            user = User(
                name='John Doe',
                email='john@example.com',
                password=User.generate_password_hash('SecurePassword123!'),
                user_role='user'
            )
            db.session.add(user)
            db.session.commit()
        
        # Try to login with wrong password
        login_payload = {
            'email': 'john@example.com',
            'password': 'WrongPassword123!'
        }
        
        response = client.post(
            '/api/v1/login',
            data=json.dumps(login_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_login_user_not_found(self, client):
        """Test login with non-existent user"""
        login_payload = {
            'email': 'nonexistent@example.com',
            'password': 'AnyPassword123!'
        }
        
        response = client.post(
            '/api/v1/login',
            data=json.dumps(login_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 404
    
    def test_login_missing_email(self, client):
        """Test login without email"""
        login_payload = {
            'password': 'SomePassword123!'
        }
        
        response = client.post(
            '/api/v1/login',
            data=json.dumps(login_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_login_missing_password(self, client):
        """Test login without password"""
        login_payload = {
            'email': 'john@example.com'
        }
        
        response = client.post(
            '/api/v1/login',
            data=json.dumps(login_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code >= 400
    
    def test_admin_token_includes_admin_claims(self, client, app):
        """Test that admin user token includes admin claims"""
        with app.app_context():
            user = User(
                name='Admin User',
                email='admin@example.com',
                password=User.generate_password_hash('AdminPassword123!'),
                user_role='admin'
            )
            db.session.add(user)
            db.session.commit()
        
        login_payload = {
            'email': 'admin@example.com',
            'password': 'AdminPassword123!'
        }
        
        response = client.post(
            '/api/v1/login',
            data=json.dumps(login_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['value']['user_role'] == 'admin'


@pytest.mark.unit
class TestGetUser:
    """Test retrieving user information"""
    
    def test_get_user_success(self, client, auth_token, app):
        """Test successfully retrieving a user"""
        with app.app_context():
            user = User(
                name='John Doe',
                email='john@example.com',
                password=User.generate_password_hash('SecurePassword123!'),
                user_role='user'
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id
        
        response = client.get(
            f'/api/v1/users/{user_id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['email'] == 'john@example.com'
        assert data['name'] == 'John Doe'
    
    def test_get_user_not_found(self, client, auth_token):
        """Test retrieving non-existent user"""
        response = client.get(
            '/api/v1/users/99999',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 404
    
    def test_get_all_users(self, client, app):
        """Test retrieving all users"""
        with app.app_context():
            for i in range(3):
                user = User(
                    name=f'User {i}',
                    email=f'user{i}@example.com',
                    password=User.generate_password_hash('Password123!'),
                    user_role='user'
                )
                db.session.add(user)
            db.session.commit()

        response = client.get('/api/v1/users')
        
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 3


@pytest.mark.unit
class TestRoleManagement:
    """Test user role promotions and management"""
    
    def test_promote_to_admin(self, client, auth_token, app):
        """Test promoting a user to admin"""
        with app.app_context():
            user = User(
                name='Regular User',
                email='user@example.com',
                password=User.generate_password_hash('Password123!'),
                user_role='user'
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id
        
        response = client.put(
            f'/api/v1/admin/{user_id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 204]
        
        with app.app_context():
            updated_user = db.session.get(User, user_id)
            assert updated_user.user_role == 'admin'
    
    def test_promote_to_super_admin(self, client, auth_token, app):
        """Test promoting a user to super admin"""
        with app.app_context():
            user = User(
                name='Admin User',
                email='admin@example.com',
                password=User.generate_password_hash('Password123!'),
                user_role='admin'
            )
            db.session.add(user)
            db.session.commit()
            user_id = user.id
        
        response = client.put(
            f'/api/v1/super_admin/{user_id}',
            headers=get_auth_headers(auth_token)
        )
        
        assert response.status_code in [200, 204]
        
        with app.app_context():
            updated_user = db.session.get(User, user_id)
            assert updated_user.user_role == 'super_admin'
    
    def test_get_employees_list(self, client, auth_token, app):
        """Test retrieving the list of employees"""
        with app.app_context():
            for i in range(5):
                user = User(
                    name=f'Employee {i}',
                    email=f'emp{i}@example.com',
                    password=User.generate_password_hash('Password123!'),
                    user_role='admin' if i % 2 == 0 else 'user'
                )
                db.session.add(user)
            db.session.commit()

        response = client.get(
            '/api/v1/employees',
            headers=get_auth_headers(auth_token)
        )

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 3
