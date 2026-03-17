from app.Admin.model import User
from app.schemas.schemas import admin_schema, admins_schema
from app.database.database import db
from flask import jsonify, make_response



class UserController:
    model = User

    @classmethod
    def create_user(cls, data, session):
        
        password = User.generate_password_hash(data.get('password'))
        
        user = cls.model(
            name=data.get('name'),
            email=data.get('email'),
            password=password,
            user_role= "user"
        )
        

        if session.query(User.query.filter(User.email == user.email).exists()).scalar():
            
            return make_response(jsonify({
            "status": 409,
            "message": "user with that email already exists"
        }), 409)
        

        user.save(session)
       
        return admin_schema.dump(user), 201
    

    def save(self, session):
        session.add(self)
        session.commit()

    @staticmethod
    def get_admin():
        user_role = 'super_admin'
        employe = User.query.filter_by(user_role=user_role).all()
        result = admins_schema.dump(employe)

        return result

    @classmethod
    def promote_user(cls, id, session):

        user_role = "super_admin"

        admin = User.get_one(cls.model, id, session)

        if admin is None:
            return 

        admin.user_role = user_role


        db.session.commit()

        return admin_schema.dump(admin), 200
    @classmethod
    def user_admin(cls, id, session):

        user_role = "admin"

        admin = User.get_one(cls.model, id, session)

        if admin is None:
            return

        admin.user_role = user_role


        db.session.commit()

        return admin_schema.dump(admin), 200
    @classmethod
    def get_user_by_id(cls, id, session):
        user = User.get_one(cls.model, id, session)
    
        if user is  None:
            
            return         
        return user
        
        

    @classmethod
    def get_all_users(cls, session):
        users = User.get_all(cls.model, session)

        return admins_schema.dump(users), 200
        
        