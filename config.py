import os
from datetime import timedelta

class Config:
    """Base configuration"""
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # DhanHQ Configuration
    DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID', '1106299230')
    DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN', '')
    
    # OAuth Configuration
    DHAN_OAUTH_CLIENT_ID = os.getenv('DHAN_OAUTH_CLIENT_ID', '')
    DHAN_OAUTH_CLIENT_SECRET = os.getenv('DHAN_OAUTH_CLIENT_SECRET', '')
    DHAN_OAUTH_REDIRECT_URI = os.getenv('DHAN_OAUTH_REDIRECT_URI', 'http://localhost:5000/auth/callback')
    
    # eDIS Configuration
    DHAN_EDIS_CLIENT_ID = os.getenv('DHAN_EDIS_CLIENT_ID', '')
    DHAN_EDIS_CLIENT_SECRET = os.getenv('DHAN_EDIS_CLIENT_SECRET', '')
    
    # Authentication Configuration
    DHAN_TOTP_SECRET = os.getenv('DHAN_TOTP_SECRET', '')
    
    # Logging Configuration
    LOG_FILE = os.getenv('LOG_FILE', 'app.log')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Market Indices
    INDICES = {
        'NIFTY': 13,
        'BANKNIFTY': 25,
        'FINNIFTY': 27,
        'MIDCPNIFTY': 442,
        'SENSEX': 51,
        'BANKEX': 49
    }
    
    # API Configuration
    DEBUG = False
    TESTING = False
    FLASK_ENV = 'production'

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    FLASK_ENV = 'development'
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    FLASK_ENV = 'production'

class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    FLASK_ENV = 'testing'
    WTF_CSRF_ENABLED = False

def get_config():
    """Get configuration based on environment"""
    env = os.getenv('FLASK_ENV', 'development').lower()
    
    if env == 'production':
        return ProductionConfig()
    elif env == 'testing':
        return TestingConfig()
    else:
        return DevelopmentConfig()
