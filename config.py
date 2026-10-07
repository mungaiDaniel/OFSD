import os
from decimal import Decimal

from dotenv import load_dotenv

# Load secrets/settings from a local .env file (next to this file) into
# os.environ. Real environment variables still win if both are set.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

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

        # Safety net: never let a local/test run touch a real SMTP server.
        # Flask-Mail checks this before opening a connection — when True,
        # mail.send() is a no-op (message goes to mail.outbox instead).
        MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'True').lower() == 'true'

        # Flask-Mail defaults MAIL_DEBUG to app.debug, which dumps the full raw SMTP
        # conversation (including base64 attachment bodies) to stdout on every send —
        # explicitly off unless someone needs it for troubleshooting SMTP auth.
        MAIL_DEBUG = os.environ.get('MAIL_DEBUG', 'False').lower() == 'true'

        # Send-queue throttle: Confirm just marks an email 'Queued'; this is how often
        # and how many the background scheduler actually sends per run. Defaults picked
        # to stay comfortably under Office365's per-mailbox throttling threshold.
        EMAIL_QUEUE_INTERVAL_MINUTES = int(os.environ.get('EMAIL_QUEUE_INTERVAL_MINUTES', 5))
        EMAIL_QUEUE_BATCH_SIZE = int(os.environ.get('EMAIL_QUEUE_BATCH_SIZE', 100))

        # Automatic daily DB backups (pg_dump -> OneDrive). Off by default in every
        # environment until an Azure AD app registration + OneDrive target are set up
        # and DB_BACKUP_ENABLED is explicitly set to true.
        DB_BACKUP_ENABLED = os.environ.get('DB_BACKUP_ENABLED', 'False').lower() == 'true'
        DB_BACKUP_HOUR_UTC = int(os.environ.get('DB_BACKUP_HOUR_UTC', 1))
        DB_BACKUP_MINUTE_UTC = int(os.environ.get('DB_BACKUP_MINUTE_UTC', 0))
        PG_DUMP_PATH = os.environ.get('PG_DUMP_PATH') or 'pg_dump'
        AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID')
        AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
        AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
        ONEDRIVE_USER_ID = os.environ.get('ONEDRIVE_USER_ID')
        ONEDRIVE_BACKUP_FOLDER = os.environ.get('ONEDRIVE_BACKUP_FOLDER') or 'OFSD-DB-Backups'

        # Minimum deposit (before fees) accepted into a SHARES (DPRP) batch.
        MIN_DEPOSIT_USD = Decimal(os.environ.get('MIN_DEPOSIT_USD', '2000'))


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

        # TEMPORARY: default flipped to allow real sends, at the user's explicit request,
        # while they test delivery to their own personal inboxes (not real investor
        # addresses). Revert this default back to 'True' once delivery is confirmed working,
        # so later testing against the seeded real-investor data stays safe by default.
        MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'False').lower() == 'true'

        # Flask-Mail defaults MAIL_DEBUG to app.debug, which dumps the full raw SMTP
        # conversation (including base64 attachment bodies) to stdout on every send —
        # explicitly off unless someone needs it for troubleshooting SMTP auth.
        MAIL_DEBUG = os.environ.get('MAIL_DEBUG', 'False').lower() == 'true'

        # Send-queue throttle: Confirm just marks an email 'Queued'; this is how often
        # and how many the background scheduler actually sends per run. Defaults picked
        # to stay comfortably under Office365's per-mailbox throttling threshold.
        EMAIL_QUEUE_INTERVAL_MINUTES = int(os.environ.get('EMAIL_QUEUE_INTERVAL_MINUTES', 5))
        EMAIL_QUEUE_BATCH_SIZE = int(os.environ.get('EMAIL_QUEUE_BATCH_SIZE', 100))

        # Automatic daily DB backups (pg_dump -> OneDrive). Off by default until
        # DB_BACKUP_ENABLED plus the Azure/OneDrive env vars below are set.
        DB_BACKUP_ENABLED = os.environ.get('DB_BACKUP_ENABLED', 'False').lower() == 'true'
        DB_BACKUP_HOUR_UTC = int(os.environ.get('DB_BACKUP_HOUR_UTC', 1))
        DB_BACKUP_MINUTE_UTC = int(os.environ.get('DB_BACKUP_MINUTE_UTC', 0))
        PG_DUMP_PATH = os.environ.get('PG_DUMP_PATH') or 'pg_dump'
        AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID')
        AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
        AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
        ONEDRIVE_USER_ID = os.environ.get('ONEDRIVE_USER_ID')
        ONEDRIVE_BACKUP_FOLDER = os.environ.get('ONEDRIVE_BACKUP_FOLDER') or 'OFSD-DB-Backups'

        # Minimum deposit (before fees) accepted into a SHARES (DPRP) batch.
        MIN_DEPOSIT_USD = Decimal(os.environ.get('MIN_DEPOSIT_USD', '2000'))

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

        # Real sends stay on in production unless explicitly overridden.
        MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'False').lower() == 'true'

        # DEBUG=False in production already keeps Flask-Mail's default debug off,
        # but pin it explicitly so a stray env var can't turn on SMTP conversation logging.
        MAIL_DEBUG = os.environ.get('MAIL_DEBUG', 'False').lower() == 'true'

        # Send-queue throttle: Confirm just marks an email 'Queued'; this is how often
        # and how many the background scheduler actually sends per run. Defaults picked
        # to stay comfortably under Office365's per-mailbox throttling threshold.
        EMAIL_QUEUE_INTERVAL_MINUTES = int(os.environ.get('EMAIL_QUEUE_INTERVAL_MINUTES', 5))
        EMAIL_QUEUE_BATCH_SIZE = int(os.environ.get('EMAIL_QUEUE_BATCH_SIZE', 100))

        # Automatic daily DB backups (pg_dump -> OneDrive). Off by default even in
        # production until DB_BACKUP_ENABLED plus the Azure/OneDrive env vars below
        # are explicitly set — this is a deliberate opt-in, not implied by "production".
        DB_BACKUP_ENABLED = os.environ.get('DB_BACKUP_ENABLED', 'False').lower() == 'true'
        DB_BACKUP_HOUR_UTC = int(os.environ.get('DB_BACKUP_HOUR_UTC', 1))
        DB_BACKUP_MINUTE_UTC = int(os.environ.get('DB_BACKUP_MINUTE_UTC', 0))
        PG_DUMP_PATH = os.environ.get('PG_DUMP_PATH') or 'pg_dump'
        AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID')
        AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
        AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
        ONEDRIVE_USER_ID = os.environ.get('ONEDRIVE_USER_ID')
        ONEDRIVE_BACKUP_FOLDER = os.environ.get('ONEDRIVE_BACKUP_FOLDER') or 'OFSD-DB-Backups'

        # Minimum deposit (before fees) accepted into a SHARES (DPRP) batch.
        MIN_DEPOSIT_USD = Decimal(os.environ.get('MIN_DEPOSIT_USD', '2000'))

# postgresql://salonapi_user:UDCYfmsCp7DYWk2ar4ssjzYGfGmjJf31@dpg-d0tvqoadbo4c73a7qpog-a/salonapi

# "postgresql:///osfmr"