import os
from datetime import timedelta

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")

    # Database — default to absolute path inside instance/ next to this file
    _default_db = os.path.join(_BASE_DIR, "instance", "finance.db")
    FINANCE_DB_PATH = os.environ.get("FINANCE_DB_PATH", _default_db)
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{FINANCE_DB_PATH}"

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # JSON
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    TESTING = False

    # Enforce security headers in production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


def get_config():
    """Get config based on FLASK_ENV."""
    env = os.environ.get("FLASK_ENV", "development")

    if env == "production":
        return ProductionConfig
    elif env == "testing":
        return TestingConfig
    else:
        return DevelopmentConfig
