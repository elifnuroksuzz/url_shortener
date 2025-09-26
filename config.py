"""
URL Shortener - Konfigürasyon Ayarları
Flask uygulaması için environment-based konfigürasyon yönetimi.

Bu dosya farklı ortamlar (development, production, testing) için
ayrı konfigürasyonlar sağlar ve güvenlik best practice'lerini uygular.
"""

import os
import secrets
from datetime import timedelta


class BaseConfig:
    """
    Temel konfigürasyon sınıfı
    
    Tüm ortamlar için ortak ayarları içerir.
    Diğer konfigürasyon sınıfları bundan inherit eder.
    """
    
    # Flask temel ayarları
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # SQLAlchemy ayarları
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Performance için kapalı
    SQLALCHEMY_RECORD_QUERIES = False       # Production'da kapalı
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_timeout': 20,
        'pool_recycle': -1,
        'pool_pre_ping': True  # Connection health check
    }
    
    # WTF Form ayarları
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 saat
    
    # URL Shortener özel ayarları
    SHORT_CODE_LENGTH = 6  # Kısa kod uzunluğu (varsayılan)
    SHORT_CODE_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    MAX_URL_LENGTH = 2048  # Maksimum URL uzunluğu
    CUSTOM_CODE_MAX_LENGTH = 20  # Kullanıcı tanımlı kod max uzunluk
    
    # Rate limiting (gelecekte implementasyon için)
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "100 per hour"  # IP bazında limit
    
    # Cache ayarları
    CACHE_TYPE = "simple"  # Development için basit cache
    CACHE_DEFAULT_TIMEOUT = 300  # 5 dakika
    
    # Session ayarları
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False  # HTTP için False, HTTPS için True
    SESSION_COOKIE_HTTPONLY = True  # XSS koruması
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF koruması
    
    # Upload ayarları (gelecekte file upload için)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Timezone
    TIMEZONE = 'UTC'
    
    # Email ayarları (gelecekte notifications için)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    @staticmethod
    def init_app(app):
        """
        Uygulama başlatıldığında çalışacak konfigürasyon işlemleri
        
        Args:
            app: Flask application instance
        """
        pass


class DevelopmentConfig(BaseConfig):
    """
    Development (Geliştirme) ortamı konfigürasyonu
    
    Debug mode açık, detaylı loglar, gevşek güvenlik ayarları.
    """
    
    DEBUG = True
    TESTING = False
    
    # Veritabanı - Local SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database_dev.db')
    
    # Development'ta query logları açık
    SQLALCHEMY_RECORD_QUERIES = True
    
    # Gevşek güvenlik ayarları
    WTF_CSRF_ENABLED = False  # Development'ta CSRF kapalı (opsiyonel)
    
    # Session güvenliği gevşek
    SESSION_COOKIE_SECURE = False
    
    # Rate limiting kapalı
    RATELIMIT_ENABLED = False
    
    # Detaylı error sayfaları
    PROPAGATE_EXCEPTIONS = True
    
    @staticmethod
    def init_app(app):
        """Development-specific initialization"""
        BaseConfig.init_app(app)
        
        # Development'ta detaylı logging
        import logging
        logging.basicConfig(level=logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
        app.logger.info('🚀 URL Shortener başlatıldı (Development Mode)')


class ProductionConfig(BaseConfig):
    """
    Production (Canlı) ortamı konfigürasyonu
    
    Güvenlik maksimum, performans optimizasyonları, minimal loglar.
    """
    
    DEBUG = False
    TESTING = False
    
    # Veritabanı - Environment'tan al
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database_prod.db')
    
    # SQLite için production optimizasyonları
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_timeout': 20,
        'pool_recycle': 3600,  # 1 saat
        'pool_pre_ping': True,
        'connect_args': {
            'check_same_thread': False,  # SQLite threading
            'timeout': 20  # Connection timeout
        }
    }
    
    # Güvenlik maksimum
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = True  # HTTPS gerekli
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    # Rate limiting aktif
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "50 per hour"  # Production'da daha katı
    
    # Error handling
    PROPAGATE_EXCEPTIONS = False
    
    # Cache - Production'da Redis kullanılabilir
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_REDIS_URL = os.environ.get('REDIS_URL')
    
    @staticmethod
    def init_app(app):
        """Production-specific initialization"""
        BaseConfig.init_app(app)
        
        # Production logging
        import logging
        from logging.handlers import RotatingFileHandler
        
        # File handler
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            'logs/url_shortener.log',
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('🔥 URL Shortener başlatıldı (Production Mode)')


class TestingConfig(BaseConfig):
    """
    Testing (Test) ortamı konfigürasyonu
    
    Unit test ve integration test'ler için optimizasyon.
    """
    
    DEBUG = True
    TESTING = True
    
    # Test için in-memory database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Test'ler için güvenlik gevşek
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    
    # Rate limiting kapalı
    RATELIMIT_ENABLED = False
    
    # Cache kapalı
    CACHE_TYPE = "null"
    
    # Test için kısa kod uzunluğu
    SHORT_CODE_LENGTH = 4  # Test'lerde daha kısa
    
    @staticmethod
    def init_app(app):
        """Testing-specific initialization"""
        BaseConfig.init_app(app)
        
        # Test logging
        import logging
        logging.disable(logging.CRITICAL)  # Test'lerde log gürültüsü yok


# Environment bazında config seçimi
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """
    Environment variable'a göre doğru config'i döner
    
    FLASK_ENV environment variable'ına bakar:
    - 'production' -> ProductionConfig
    - 'testing' -> TestingConfig
    - diğer/yoksa -> DevelopmentConfig (default)
    
    Returns:
        Config class: Uygun konfigürasyon sınıfı
    """
    env = os.environ.get('FLASK_ENV', 'development').lower()
    return config.get(env, config['default'])


def validate_config(app):
    """
    Konfigürasyonu validate eder ve eksik/hatalı ayarlar için warning verir
    
    Args:
        app: Flask application instance
        
    Returns:
        list: Validation error/warning mesajları
    """
    warnings = []
    
    # Secret key kontrolü
    if app.config['SECRET_KEY'] == 'dev-secret-key':
        warnings.append("⚠️  SECRET_KEY varsayılan değerde! Production'da değiştirin.")
    
    # HTTPS kontrolü (production)
    if not app.debug and not app.config.get('SESSION_COOKIE_SECURE'):
        warnings.append("⚠️  Production'da HTTPS kullanın (SESSION_COOKIE_SECURE=True)")
    
    # Database URL kontrolü
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'sqlite:///:memory:' in db_url and not app.config.get('TESTING'):
        warnings.append("⚠️  In-memory database production'da kullanılmamalı!")
    
    # Rate limiting kontrolü
    if not app.debug and not app.config.get('RATELIMIT_ENABLED'):
        warnings.append("⚠️  Production'da rate limiting etkinleştirin!")
    
    return warnings


# Development için .env dosyası örneği
ENV_EXAMPLE = """
# URL Shortener - Environment Variables Örneği
# Bu dosyayı .env olarak kopyalayın ve değerleri güncelleyin

# Flask ayarları
FLASK_ENV=development
SECRET_KEY=your-super-secret-key-here

# Veritabanı
DATABASE_URL=sqlite:///database.db
DEV_DATABASE_URL=sqlite:///database_dev.db

# Email (opsiyonel)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# Cache (opsiyonel)
CACHE_TYPE=simple
REDIS_URL=redis://localhost:6379/0

# Rate Limiting
RATELIMIT_ENABLED=true

# Güvenlik
WTF_CSRF_ENABLED=true
SESSION_COOKIE_SECURE=false
"""


if __name__ == "__main__":
    # Config test'i
    print("🔧 Konfigürasyon Test Ediliyor...\n")
    
    for env_name, config_class in config.items():
        if env_name == 'default':
            continue
        print(f"📋 {env_name.upper()} Config:")
        print(f"   DEBUG: {config_class.DEBUG}")
        print(f"   TESTING: {config_class.TESTING}")
        print(f"   DATABASE: {config_class.SQLALCHEMY_DATABASE_URI}")
        print(f"   SHORT_CODE_LENGTH: {config_class.SHORT_CODE_LENGTH}")
        print()
    
    print("✅ Tüm konfigürasyonlar yüklendi!")