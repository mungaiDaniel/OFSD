import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum
from app.database.database import db
from base_model import Base
from flask_jwt_extended import create_access_token
from passlib.handlers.md5_crypt import md5_crypt


class Admin(str, Enum):
    super_admin = 'super_admin'
    admin = 'admin'
    user = 'user'


class User(Base, db.Model):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True)
    password = Column(String(1000))
    user_role = Column(String, Enum('super_admin', 'admin', 'user', name='user_roles'), default='user')
    created = Column(DateTime, default=datetime.datetime.now())

    def generate_auth_token(self, permission_level):

        if permission_level == 2:

            token = create_access_token(identity=self.email, additional_claims={'admin': 2})

            return token
        elif permission_level == 1:

            token = create_access_token(identity=self.email, additional_claims={'admin': 1})

            return token

        return create_access_token(identity=self.email, additional_claims={'admin': 0})

    @staticmethod
    def generate_password_hash(password):

        h = md5_crypt.hash(password)

        return h

    def verify_password_hash(self, password):

        return md5_crypt.verify(password, self.password)