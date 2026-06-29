import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

def init_env_secrets():
    env_path = BASE_DIR / '.env'
    example_path = BASE_DIR / '.env.example'
    if not env_path.exists() and example_path.exists():
        import shutil
        shutil.copy(example_path, env_path)
        
    if env_path.exists():
        content = env_path.read_text()
        modified = False
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith('SECRET_KEY='):
                val = line.split('=', 1)[1].strip()
                if not val and not os.environ.get('SECRET_KEY'):
                    new_key = secrets.token_hex(32)
                    lines[i] = f'SECRET_KEY={new_key}'
                    os.environ['SECRET_KEY'] = new_key
                    modified = True
            elif line.startswith('SECURITY_PASSWORD_SALT='):
                val = line.split('=', 1)[1].strip()
                if not val and not os.environ.get('SECURITY_PASSWORD_SALT'):
                    new_salt = secrets.token_hex(16)
                    lines[i] = f'SECURITY_PASSWORD_SALT={new_salt}'
                    os.environ['SECURITY_PASSWORD_SALT'] = new_salt
                    modified = True
        if modified:
            env_path.write_text('\n'.join(lines) + '\n')

init_env_secrets()
load_dotenv(BASE_DIR / '.env')

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Hermes Config
    HERMES_BASE_URL = os.environ.get('HERMES_BASE_URL') or 'https://hermesbot.pythonanywhere.com'
    HERMES_API_KEY = os.environ.get('HERMES_API_KEY') or None
    HERMES_EMAILBOT_ID = os.environ.get('HERMES_EMAILBOT_ID') or None

    # Initial Admin Config
    INITIAL_ADMIN_EMAIL = os.environ.get('INITIAL_ADMIN_EMAIL') or 'indrajitghosh912@gmail.com'
    INITIAL_ADMIN_USERNAME = os.environ.get('INITIAL_ADMIN_USERNAME') or 'ghostrix'
    
    # Mail Config (Legacy/Fallback)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'localhost'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 8025)
    MAIL_USE_TLS = (os.environ.get('MAIL_USE_TLS') or 'true').lower() in ('true', '1', 't')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or None
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@expensewise.local'
    
    # Caching Config
    CACHE_TYPE = os.environ.get('CACHE_TYPE') or 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT') or 300)
    
    # Limiter Config
    RATELIMIT_DEFAULT_LIMITS = ["200 per day", "50 per hour"]
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI') or 'memory://'

    # Security Config (WTF)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour token validity

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    
    # Check if DATABASE_URL is set and not empty, otherwise fallback to local SQLite
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.strip():
        SQLALCHEMY_DATABASE_URI = db_url
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'expensewise.db'}"

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    # Enforce SSL in Talisman for Production
    PREFERRED_URL_SCHEME = 'https'
    
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.strip():
        SQLALCHEMY_DATABASE_URI = db_url
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'expensewise.db'}"

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
