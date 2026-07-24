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
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_JWT_ISSUER = (
    os.getenv("SUPABASE_JWT_ISSUER")
    or (f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else "")
).strip().rstrip("/")

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

IS_PROTECTED_DEPLOYMENT = DEPLOYMENT_ENV in {"staging", "production"}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = IS_PROTECTED_DEPLOYMENT
CSRF_COOKIE_SECURE = IS_PROTECTED_DEPLOYMENT
SECURE_HSTS_SECONDS = (
    int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
    if IS_PROTECTED_DEPLOYMENT
    else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Caddy owns HTTP-to-HTTPS redirects; enabling Django redirects would break
# the container's private HTTP readiness probe.
SECURE_SSL_REDIRECT = False

validate_runtime_configuration(
    deployment_environment=DEPLOYMENT_ENV,
    debug=DEBUG,
    secret_key_env=SECRET_KEY_ENV,
    allowed_hosts_env=ALLOWED_HOSTS_ENV,
    supabase_url=SUPABASE_URL,
    supabase_jwt_issuer=SUPABASE_JWT_ISSUER,
)

INSTALLED_APPS = [
    "django.contrib.admin",
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
        "OPTIONS": {
            "timeout": int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "5000")) / 1000,
        },
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
        "route_report_user_burst": os.getenv(
            "ROUTE_REPORT_USER_BURST_RATE", "5/minute"
        ),
        "route_report_user_hourly": os.getenv(
            "ROUTE_REPORT_USER_HOURLY_RATE", "20/hour"
        ),
        "route_report_user_daily": os.getenv(
            "ROUTE_REPORT_USER_DAILY_RATE", "25/day"
        ),
        "route_report_ip": os.getenv("ROUTE_REPORT_IP_RATE", "100/hour"),
        "route_report_ip_daily": os.getenv(
            "ROUTE_REPORT_IP_DAILY_RATE", "100/day"
        ),
        "route_report_global": os.getenv("ROUTE_REPORT_GLOBAL_RATE", ""),
        "user_data_user_burst": os.getenv(
            "USER_DATA_USER_BURST_RATE",
            "60/minute",
        ),
        "user_data_user_daily": os.getenv(
            "USER_DATA_USER_DAILY_RATE",
            "1000/day",
        ),
        "user_data_ip": os.getenv("USER_DATA_IP_RATE", "2000/day"),
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
ROUTING_BUILD_DATE = os.getenv("ROUTING_BUILD_DATE", "")
RALLYIFY_API_VERSION = os.getenv("RALLYIFY_API_VERSION", "beta")
ROUTE_MAX_ENDPOINT_SNAP_METRES = float(
    os.getenv("ROUTE_MAX_ENDPOINT_SNAP_METRES", "5000")
)
ROUTE_MAX_GEOMETRY_GAP_METRES = float(
    os.getenv("ROUTE_MAX_GEOMETRY_GAP_METRES", "100000")
)
ROUTE_DIAGNOSTIC_RETENTION_DAYS = int(
    os.getenv("ROUTE_DIAGNOSTIC_RETENTION_DAYS", "14")
)
ROUTE_REPORT_EXACT_RETENTION_DAYS = int(
    os.getenv("ROUTE_REPORT_EXACT_RETENTION_DAYS", "30")
)
ROUTE_REPORT_SUMMARY_RETENTION_DAYS = int(
    os.getenv("ROUTE_REPORT_SUMMARY_RETENTION_DAYS", "90")
)
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated").strip()
SUPABASE_JWKS_URL = (
    f"{SUPABASE_JWT_ISSUER}/.well-known/jwks.json" if SUPABASE_JWT_ISSUER else ""
)
SUPABASE_JWT_ALGORITHMS = ["ES256", "RS256"]
SUPABASE_JWKS_CACHE_SECONDS = min(
    max(int(os.getenv("SUPABASE_JWKS_CACHE_SECONDS", "600")), 60),
    600,
)
SUPABASE_JWKS_TIMEOUT_SECONDS = int(os.getenv("SUPABASE_JWKS_TIMEOUT_SECONDS", "3"))
SUPABASE_JWT_LEEWAY_SECONDS = int(os.getenv("SUPABASE_JWT_LEEWAY_SECONDS", "30"))
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "5000"))
ROUTE_REPORT_MAX_JSON_DEPTH = int(os.getenv("ROUTE_REPORT_MAX_JSON_DEPTH", "10"))
USER_DATA_MAX_VEHICLES = int(os.getenv("USER_DATA_MAX_VEHICLES", "20"))
DRIVE_HISTORY_DEFAULT_PAGE_SIZE = int(
    os.getenv("DRIVE_HISTORY_DEFAULT_PAGE_SIZE", "25")
)
DRIVE_HISTORY_MAX_PAGE_SIZE = int(os.getenv("DRIVE_HISTORY_MAX_PAGE_SIZE", "100"))
