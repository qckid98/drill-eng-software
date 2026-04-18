"""
Django settings for drilltime_app project.

Drilling Proposal (Drilling Time) web application — migrated from the
`DrillTime_ BDA-G3 - Cluster BDA-D1.xlsx` workbook used by PT. Pertamina EP
Drilling Engineers (form DEP/Form/DE/01/DT v2.4/2017).
"""

import logging
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---
_default_key = "dev-insecure-key-change-in-production-please-seriously"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _default_key)
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

if not DEBUG and SECRET_KEY == _default_key:
    raise RuntimeError(
        "DJANGO_SECRET_KEY env var must be set in production. "
        "Generate one with: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

# --- Applications ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "django_htmx",
    # Local
    "accounts",
    "masterdata",
    "wells",
    "proposals",
    "afe",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "drilltime_app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "drilltime_app.wsgi.application"

# --- Database ---
# Defaults to SQLite for quick local runs; flip to Postgres via env vars.
if os.environ.get("DATABASE_URL"):
    # Very small inline parser to avoid an extra dependency
    import re
    m = re.match(
        r"postgres(?:ql)?://(?P<user>[^:]+):(?P<pw>[^@]+)@(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<name>[^?]+)",
        os.environ["DATABASE_URL"],
    )
    if not m:
        raise ValueError("DATABASE_URL must be a postgres:// URL")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": m.group("name"),
            "USER": m.group("user"),
            "PASSWORD": m.group("pw"),
            "HOST": m.group("host"),
            "PORT": m.group("port") or "5432",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Auth ---
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "proposals:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N ---
LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

# --- Static ---
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Security hardening (production) ---
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# --- File upload limits ---
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "drilltime.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django.security": {
            "handlers": ["console", "file"],
            "level": "WARNING",
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "WARNING",
        },
        "proposals": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
        "afe": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
    },
}

# --- App-specific ---
DRILLTIME_DOC_PREFIX = "DEP/Form/DE/01/DT"
DRILLTIME_FORM_VERSION = "2.4/2017"
AFE_DOC_PREFIX = "DEP/Form/AFE"
AFE_FORM_VERSION = "2017"
