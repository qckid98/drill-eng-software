"""
Django settings for drilltime_app project.

Drilling Proposal (Drilling Time) web application — migrated from the
`DrillTime_ BDA-G3 - Cluster BDA-D1.xlsx` workbook used by PT. Pertamina EP
Drilling Engineers (form DEP/Form/DE/01/DT v2.4/2017).
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-key-change-in-production-please-seriously",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

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
    "rest_framework",
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

# --- App-specific ---
DRILLTIME_DOC_PREFIX = "DEP/Form/DE/01/DT"
DRILLTIME_FORM_VERSION = "2.4/2017"
AFE_DOC_PREFIX = "DEP/Form/AFE"
AFE_FORM_VERSION = "2017"
