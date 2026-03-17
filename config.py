import os

postgre_local_base = "postgresql://postgres:username@localhost/salons"
    
class TestingConfig():
        
        TESTING = True
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'testing-secret-key-minimum-32-bytes-long-required-securely'
        SQLALCHEMY_DATABASE_URI = "postgresql://postgres:username@localhost/offsho_test"
    
        
class DevelopmentConfig():
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-minimum-32-bytes-long-required-for-secure-jwt'
        SQLALCHEMY_DATABASE_URI = "postgresql://postgres:username@localhost/offshow_dev"
        DEBUG = True
        DEVELOPMENT = True      
        
class ProductionConfig():
        
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'prod-secret-key-minimum-32-bytes-long-required-for-secure-jwt-operations'
        DEBUG = False
        SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI")

# postgresql://salonapi_user:UDCYfmsCp7DYWk2ar4ssjzYGfGmjJf31@dpg-d0tvqoadbo4c73a7qpog-a/salonapi