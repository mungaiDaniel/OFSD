from app.Admin.controllers import UserController
from flask import request, Blueprint
from app.database.database import db
from app.schemas.schemas import admin_schema, admins_schema
from app.Admin.model import User
import logging
from flask import jsonify, make_response
import app.utils.responses as resp
from app.utils.responses import m_return
from flask_jwt_extended import create_refresh_token, jwt_required

user_v1 = Blueprint("user_v1", __name__, url_prefix='/api/v1')

@user_v1.route('/users', methods=['POST'])
def add_user():
    data = request.get_json()
    session = db.session
    return UserController.create_user(data, session=session)


@user_v1.route('/users/<int:id>', methods=['GET'])
@jwt_required()
def get_one(id):
    session = db.session
    result = UserController.get_user_by_id(id, session=session)
    if result:

        return admin_schema.dump(result)
    return make_response(jsonify({
            "status": 404,
            "message": "user doesn't exist"
        }), 404)

@user_v1.route('/users', methods=['GET'])
# @jwt_required()
def get_all():
    session = db.session

    return UserController.get_all_users(session=session)


@user_v1.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    try:
        email = data['email']
        password = (data['password'])

    except Exception as why:

        logging.info('Email or password is wrong' + str(why))

        return m_return(http_code=resp.MISSED_PARAMETERS['http_code'], message=resp.MISSED_PARAMETERS['message'],
                        code=resp.MISSED_PARAMETERS['code'])

    user = User.query.filter_by(email=email).first()

    if user is None:
        return m_return(http_code=resp.USER_DOES_NOT_EXIST['http_code'],
                        message=resp.USER_DOES_NOT_EXIST['message'],
                        code=resp.USER_DOES_NOT_EXIST['code'])

    if not user.verify_password_hash(password):
        return m_return(http_code=resp.CREDENTIALS_ERROR_999['http_code'],
                        message=resp.CREDENTIALS_ERROR_999['message'], code=resp.CREDENTIALS_ERROR_999['code'])

    if user.user_role == 'user':

        access_token = user.generate_auth_token(0)

    elif user.user_role == 'admin':

        # Generate access token. This method takes boolean value for checking admin or normal user. Admin: 1 or 0.
        access_token = user.generate_auth_token(1)

    elif user.user_role == 'super_admin':

        # Generate access token. This method takes boolean value for checking admin or normal user. Admin: 2, 1, 0.
        access_token = user.generate_auth_token(2)

    else:

        # Return permission denied error.
        return m_return(http_code=resp.PERMISSION_DENIED['http_code'], message=resp.PERMISSION_DENIED['message'],
                        code=resp.PERMISSION_DENIED['code'])

    refresh_token = create_refresh_token(identity={'email': email})
    

    return m_return(http_code=resp.SUCCESS['http_code'],
                    message=resp.SUCCESS['message'],
                    value={'access_token': access_token, 'refresh_token': refresh_token, 'user_role':user.user_role})


@user_v1.route('/super_admin/<int:id>', methods=['PUT'])
# @jwt_required()
def superAdmin(id):
    session = db.session

    admin = UserController.promote_user(id, session=session)

    if admin is None:
            return make_response(jsonify({
            "status": 404,
            "message": "user doesn't exist"
        }), 404)

    return admin

@user_v1.route('/admin/<int:id>', methods=['PUT'])
@jwt_required()
def make_assisstance(id):

    session = db.session

    admin = UserController.user_admin(id, session=session)

    if admin is None:
            return make_response(jsonify({
            "status": 404,
            "message": "user doesn't exist"
        }), 404)

    return admin


@user_v1.route('/employees', methods=['GET'])
@jwt_required()
def Admin():
    results = UserController.get_admin()

    return results