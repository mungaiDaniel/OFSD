import os

postgre_local_base = "postgresql://postgres:username@localhost/salons"
    
class TestingConfig():
        
        TESTING = True
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'testing-secret-key-minimum-32-bytes-long-required-securely'
        SQLALCHEMY_DATABASE_URI = "postgresql://postgres:username@localhost/test-offshore"
        
        # Email configuration
        MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.office365.com'
        MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
        MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
        MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
        MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'wealthmgt@aib-axysafrica.com'
        MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
        MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'wealthmgt@aib-axysafrica.com'
        MAIL_BCC = os.environ.get('MAIL_BCC') or 'invest@aib-axysafrica.com'
        
        # Email manual approval flag
        MANUAL_EMAIL_APPROVAL = True
        
        
class DevelopmentConfig():
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-minimum-32-bytes-long-required-for-secure-jwt'
        # Allow DATABASE_URI override (e.g. create_super.py, local prod-like DB)
        SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI") or "postgresql://postgres:username@localhost/offshore"
        DEBUG = True
        DEVELOPMENT = True      
        
        # Email configuration (Office 365)
        MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.office365.com'
        MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
        MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
        MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
        MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'wealthmgt@aib-axysafrica.com'
        MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'Compaqxp1!'
        MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'wealthmgt@aib-axysafrica.com'
        MAIL_BCC = os.environ.get('MAIL_BCC') or 'invest@aib-axysafrica.com'
        
        # Email manual approval flag
        MANUAL_EMAIL_APPROVAL = True
        
class ProductionConfig():
        
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'prod-secret-key-minimum-32-bytes-long-required-for-secure-jwt-operations'
        DEBUG = False
        SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI")
        
        # Email configuration
        MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
        MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
        MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
        MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
        MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
        MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
        MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'wealthmgt@aib-axysafrica.com'
        MAIL_BCC = os.environ.get('MAIL_BCC') or 'invest@aib-axysafrica.com'

        # Email manual approval flag
        MANUAL_EMAIL_APPROVAL = os.environ.get('MANUAL_EMAIL_APPROVAL', 'True').lower() == 'true'

# postgresql://salonapi_user:UDCYfmsCp7DYWk2ar4ssjzYGfGmjJf31@dpg-d0tvqoadbo4c73a7qpog-a/salonapi

# "postgresql:///osfmr"