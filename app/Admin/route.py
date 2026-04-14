from app.Admin.controllers import UserController
from flask import request, Blueprint
from app.database.database import db
from app.schemas.schemas import admin_schema, admins_schema
from app.Admin.model import User
import logging
from flask import jsonify, make_response
import app.utils.responses as resp
from app.utils.responses import m_return
from flask_jwt_extended import create_refresh_token, jwt_required, get_jwt
from sqlalchemy import func

user_v1 = Blueprint("user_v1", __name__, url_prefix='/')

@user_v1.route('/api/v1/users', methods=['POST'])
def add_user():
    data = request.get_json()
    session = db.session
    return UserController.create_user(data, session=session)


@user_v1.route('/api/v1/users/<int:id>', methods=['GET'])
@jwt_required()
def get_one(id):
    deny = _require_superadmin()
    if deny:
        return deny
    session = db.session
    result = UserController.get_user_by_id(id, session=session)
    if result:
        return make_response(jsonify(admin_schema.dump(result)), 200)
    return make_response(jsonify({
            "status": 404,
            "message": "user doesn't exist"
        }), 404)

@user_v1.route('/api/v1/users', methods=['GET'])
@jwt_required()
def get_all():
    deny = _require_superadmin()
    if deny:
        return deny
    session = db.session

    return UserController.get_all_users(session=session)


@user_v1.route('/api/v1/login', methods=['POST'])
def login():
    data = request.get_json()
    
    try:
        email = str(data['email']).strip().lower()
        password = (data['password'])

    except Exception as why:

        logging.info('Email or password is wrong' + str(why))

        return m_return(http_code=resp.MISSED_PARAMETERS['http_code'], message=resp.MISSED_PARAMETERS['message'],
                        code=resp.MISSED_PARAMETERS['code'])

    user = User.query.filter(func.lower(User.email) == email).first()

    if user is None:
        return m_return(http_code=resp.USER_DOES_NOT_EXIST['http_code'],
                        message=resp.USER_DOES_NOT_EXIST['message'],
                        code=resp.USER_DOES_NOT_EXIST['code'])

    if not user.verify_password_hash(password):
        return m_return(http_code=resp.CREDENTIALS_ERROR_999['http_code'],
                        message=resp.CREDENTIALS_ERROR_999['message'], code=resp.CREDENTIALS_ERROR_999['code'])

    if getattr(user, "status", "active") != "active":
        return make_response(jsonify({
            "status": 403,
            "message": "Your account is pending administrator approval."
        }), 403)

    if user.role == 'user':

        access_token = user.generate_auth_token(0)

    elif user.role == 'admin':

        # Generate access token. This method takes boolean value for checking admin or normal user. Admin: 1 or 0.
        access_token = user.generate_auth_token(1)

    elif user.role == 'super_admin':

        # Generate access token. This method takes boolean value for checking admin or normal user. Admin: 2, 1, 0.
        access_token = user.generate_auth_token(2)

    else:

        # Return permission denied error.
        return m_return(http_code=resp.PERMISSION_DENIED['http_code'], message=resp.PERMISSION_DENIED['message'],
                        code=resp.PERMISSION_DENIED['code'])

    refresh_token = create_refresh_token(identity=email)
    

    return m_return(http_code=resp.SUCCESS['http_code'],
                    message=resp.SUCCESS['message'],
                    value={
                        'access_token': access_token,
                        'refresh_token': refresh_token,
                        # Keep `user_role` for frontend compatibility, but source of truth is DB column `role`
                        'user_role': user.role,
                        'role': user.role,
                        'name': user.name,
                    })
    session = db.session
    admin = UserController.promote_user(id, session=session)
    if admin is None:
        return make_response(jsonify({
            "status": 404,
            "message": "user doesn't exist"
        }), 404)
    # admin is a tuple: (schema_dump, status_code)
    if isinstance(admin, tuple):
        return make_response(jsonify(admin[0]), admin[1])
    return make_response(jsonify({"status": 500, "message": "Invalid response"}), 500)

@user_v1.route('/api/v1/admin/<int:id>', methods=['PUT'])
@jwt_required()
def make_assisstance(id):
    session = db.session
    admin = UserController.user_admin(id, session=session)
    if admin is None:
        return make_response(jsonify({
            "status": 404,
            "message": "user doesn't exist"
        }), 404)
    # admin is a tuple: (schema_dump, status_code)
    if isinstance(admin, tuple):
        return make_response(jsonify(admin[0]), admin[1])
    return make_response(jsonify({"status": 500, "message": "Invalid response"}), 500)


@user_v1.route('/api/v1/employees', methods=['GET'])
@jwt_required()
def Admin():
    results = UserController.get_admin()
    return make_response(jsonify(results), 200)


def _require_superadmin():
    claims = get_jwt() or {}
    if int(claims.get("admin", 0) or 0) != 2:
        return make_response(jsonify({"status": 403, "message": "Superadmin access required"}), 403)
    return None


@user_v1.route('/api/v1/users/<int:id>/approve', methods=['PATCH'])
@jwt_required()
def approve_user(id):
    deny = _require_superadmin()
    if deny:
        return deny

    user = User.query.get(id)
    if not user:
        return make_response(jsonify({"status": 404, "message": "user doesn't exist"}), 404)

    user.status = "active"
    db.session.commit()
    return make_response(jsonify(admin_schema.dump(user)), 200)


@user_v1.route('/api/v1/users/<int:id>/status', methods=['PATCH'])
@jwt_required()
def set_user_status(id):
    deny = _require_superadmin()
    if deny:
        return deny

    data = request.get_json() or {}
    status = data.get("status")
    if status not in ("pending", "active"):
        return make_response(jsonify({"status": 400, "message": "status must be one of: pending, active"}), 400)

    user = User.query.get(id)
    if not user:
        return make_response(jsonify({"status": 404, "message": "user doesn't exist"}), 404)

    user.status = status
    db.session.commit()
    return make_response(jsonify(admin_schema.dump(user)), 200)


@user_v1.route('/api/v1/users/<int:id>/role', methods=['PATCH'])
@jwt_required()
def set_user_role(id):
    deny = _require_superadmin()
    if deny:
        return deny

    data = request.get_json() or {}
    role = data.get("role")
    if role not in ("user", "admin", "super_admin"):
        return make_response(jsonify({"status": 400, "message": "role must be one of: user, admin, super_admin"}), 400)

    user = User.query.get(id)
    if not user:
        return make_response(jsonify({"status": 404, "message": "user doesn't exist"}), 404)

    user.role = role
    db.session.commit()
    return make_response(jsonify(admin_schema.dump(user)), 200)


@user_v1.route('/api/v1/users/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_user(id):
    deny = _require_superadmin()
    if deny:
        return deny

    user = User.query.get(id)
    if not user:
        return make_response(jsonify({"status": 404, "message": "user doesn't exist"}), 404)

    db.session.delete(user)
    db.session.commit()
    return make_response(jsonify({"status": 200, "message": "User deleted"}), 200)


@user_v1.route('/api/v1/users/<int:id>/reset-password', methods=['PATCH'])
@jwt_required()
def reset_password(id):
    deny = _require_superadmin()
    if deny:
        return deny

    data = request.get_json() or {}
    password = data.get("password")
    if not isinstance(password, str) or len(password.strip()) < 8:
        return make_response(jsonify({"status": 400, "message": "password must be at least 8 characters"}), 400)

    user = User.query.get(id)
    if not user:
        return make_response(jsonify({"status": 404, "message": "user doesn't exist"}), 404)

    user.password = User.generate_password_hash(password.strip())
    db.session.commit()
    return make_response(jsonify({"status": 200, "message": "Password reset"}), 200)