from app.Admin.model import User
from app.schemas.schemas import admin_schema, admins_schema
from app.database.database import db
from flask import jsonify, make_response
from app.utils.email_service import EmailService
from sqlalchemy import func



class UserController:
    model = User

    @classmethod
    def create_user(cls, data, session):
        # Validate required fields
        if not data.get('email'):
            return make_response(jsonify({
                "status": 400,
                "message": "email is required"
            }), 400)
        
        if not data.get('password'):
            return make_response(jsonify({
                "status": 400,
                "message": "password is required"
            }), 400)
        
        if not data.get('name'):
            return make_response(jsonify({
                "status": 400,
                "message": "name is required"
            }), 400)
        
        password = User.generate_password_hash(data.get('password'))
        email = str(data.get("email") or "").strip().lower()
        
        # Gatekeeper defaults: new signups are pending + normal user.
        user = cls.model(
            name=data.get('name'),
            email=email,
            password=password,
            role='user',
            status='pending',
        )
        

        if session.query(User.query.filter(func.lower(User.email) == email).exists()).scalar():
            
            return make_response(jsonify({
            "status": 409,
            "message": "user with that email already exists"
        }), 409)
        

        user.save(session)

        user.save(session)
       
        return admin_schema.dump(user), 201
    

    def save(self, session):
        session.add(self)
        session.commit()

    @staticmethod
    def get_admin():
        employe = User.query.filter(User.role.in_(['admin', 'super_admin'])).all()
        result = admins_schema.dump(employe)

        return result

    @classmethod
    def promote_user(cls, id, session):

        user_role = "super_admin"

        admin = User.get_one(cls.model, id, session)

        if admin is None:
            return 

        admin.role = user_role


        db.session.commit()

        return admin_schema.dump(admin), 200
    @classmethod
    def user_admin(cls, id, session):

        user_role = "admin"

        admin = User.get_one(cls.model, id, session)

        if admin is None:
            return

        admin.role = user_role


        db.session.commit()

        return admin_schema.dump(admin), 200
    @classmethod
    def get_user_by_id(cls, id, session):
        user = User.get_one(cls.model, id, session)
    
        if user is None:
            return None
        return user
        
        

    @classmethod
    def get_all_users(cls, session):
        users = User.get_all(cls.model, session)

        return admins_schema.dump(users), 200
        
        