"""Application configuration. Secrets come from environment variables / .env."""
import os
import secrets
from urllib.parse import quote_plus

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _database_uri():
    # A full DATABASE_URL (used by the tests) wins over the individual DB_* settings.
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("DB_USER", "root")
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "sams_db")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class Config:
    # If SECRET_KEY is not set a random one is generated (sessions reset on restart).
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB uploads
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 14  # 14 days

    QR_SESSION_MINUTES = int(os.environ.get("QR_SESSION_MINUTES", "10"))
    PER_PAGE = 10
    LOW_ATTENDANCE_THRESHOLD = 75  # percent

    DEPARTMENTS = ["Computer Science", "Information Technology", "Electronics"]
    YEARS = [1, 2, 3, 4]
    SECTIONS = ["A", "B", "C"]


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
