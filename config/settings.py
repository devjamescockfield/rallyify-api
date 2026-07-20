import os
from pathlib import Path

from dotenv import load_dotenv

from config.runtime import (
    DEVELOPMENT_SECRET_KEY,
    parse_boolean_environment_variable,
    validate_runtime_configuration,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DEPLOYMENT_ENV = os.getenv("DEPLOYMENT_ENV", "development").strip().lower()
SECRET_KEY_ENV = os.getenv("SECRET_KEY")
ALLOWED_HOSTS_ENV = os.getenv("ALLOWED_HOSTS")
ROUTE_REPORT_BEARER_TOKENS_ENV = os.getenv("ROUTE_REPORT_BEARER_TOKENS")

SECRET_KEY = SECRET_KEY_ENV or DEVELOPMENT_SECRET_KEY
DEBUG = parse_boolean_environment_variable(
    "DEBUG",
    os.getenv("DEBUG", "true"),
)

ALLOWED_HOSTS = [
    host.strip()
    for host in (
        ALLOWED_HOSTS_ENV or "localhost,127.0.0.1,0.0.0.0"
    ).split(",")
    if host.strip()
]

validate_runtime_configuration(
    deployment_environment=DEPLOYMENT_ENV,
    debug=DEBUG,
    secret_key_env=SECRET_KEY_ENV,
    allowed_hosts_env=ALLOWED_HOSTS_ENV,
    report_tokens_env=ROUTE_REPORT_BEARER_TOKENS_ENV,
)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DATABASE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "routing.parsers.LimitedJSONParser",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "route_burst": os.getenv("ROUTE_RATE_LIMIT_BURST", "30/minute"),
        "route_sustained": os.getenv("ROUTE_RATE_LIMIT_SUSTAINED", "500/day"),
        "route_report": os.getenv("ROUTE_REPORT_RATE_LIMIT", "10/hour"),
    },
    # Caddy is the single trusted proxy in the staging Compose deployment.
    "NUM_PROXIES": 1,
}

DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("REQUEST_BODY_MAX_BYTES", str(64 * 1024))
)

VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")
VALHALLA_TIMEOUT_SECONDS = float(os.getenv("VALHALLA_TIMEOUT_SECONDS", "10"))
VALHALLA_HEALTH_TIMEOUT_SECONDS = float(
    os.getenv("VALHALLA_HEALTH_TIMEOUT_SECONDS", "1")
)
ROUTE_SLOW_WARNING_MS = float(os.getenv("ROUTE_SLOW_WARNING_MS", "1500"))
VALHALLA_ENGINE_VERSION = os.getenv("VALHALLA_ENGINE_VERSION", "")
VALHALLA_GRAPH_BUILD_ID = os.getenv("VALHALLA_GRAPH_BUILD_ID", "")
VALHALLA_OSM_DATA_DATE = os.getenv("VALHALLA_OSM_DATA_DATE", "")
ROUTE_MAX_ENDPOINT_SNAP_METRES = float(
    os.getenv("ROUTE_MAX_ENDPOINT_SNAP_METRES", "5000")
)
ROUTE_MAX_GEOMETRY_GAP_METRES = float(
    os.getenv("ROUTE_MAX_GEOMETRY_GAP_METRES", "100000")
)
ROUTE_DIAGNOSTIC_RETENTION_DAYS = int(
    os.getenv("ROUTE_DIAGNOSTIC_RETENTION_DAYS", "14")
)
ROUTE_REPORT_RETENTION_DAYS = int(
    os.getenv("ROUTE_REPORT_RETENTION_DAYS", "14")
)
ROUTE_REPORT_BEARER_TOKENS = [
    token.strip()
    for token in (ROUTE_REPORT_BEARER_TOKENS_ENV or "").split(",")
    if token.strip()
]
