"""Django settings for the ELD trip planner backend."""

from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:  # Keep local startup usable before optional .env support is installed.
    def load_dotenv(*args, **kwargs):
        return False

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    """Split a comma-separated env var, treating a blank value as unset.

    A key present but empty (a common state for a half-filled .env) would
    otherwise wipe out the default and, for the CORS list, silently lock the
    deployed frontend out of the API.
    """
    raw = os.environ.get(name) or ""
    if not raw.strip():
        raw = default
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")

# Render injects RENDER/RENDER_EXTERNAL_HOSTNAME into every service. Keying the
# DEBUG default off it means a deploy is production-safe even when someone
# forgets to set DJANGO_DEBUG in the dashboard, while `manage.py runserver`
# locally still defaults to debug mode.
ON_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_HOSTNAME"))
DEBUG = os.environ.get("DJANGO_DEBUG", "false" if ON_RENDER else "true").lower() == "true"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com,.railway.app")
RENDER_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOSTNAME and RENDER_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_HOSTNAME)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "trips",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "eld.urls"
WSGI_APPLICATION = "eld.wsgi.application"

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
            ]
        },
    }
]

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
# Log sheets are wall-clock documents drawn in the driver's local time, so the
# engine works in naive datetimes and nothing is silently shifted to UTC.
USE_TZ = False

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": os.environ.get("API_RATE_LIMIT", "60/min")},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": __import__("datetime").timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": __import__("datetime").timedelta(days=7),
}

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,https://road-book-rouge.vercel.app"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", DEFAULT_ORIGINS)
# The production origin is always allowed. Without this, setting
# CORS_ALLOWED_ORIGINS to a dev-only value in the Render dashboard silently
# breaks the deployed frontend: the browser drops the response and the app
# reports the API as unreachable.
PRODUCTION_ORIGIN = "https://road-book-rouge.vercel.app"
if PRODUCTION_ORIGIN not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append(PRODUCTION_ORIGIN)
# Vercel preview deployments get a fresh subdomain per commit, so they are
# matched by pattern rather than listed one by one.
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://[a-z0-9-]+\.vercel\.app$"]
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL", "false").lower() == "true"

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", DEFAULT_ORIGINS) + ["https://*.vercel.app"]
if RENDER_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOSTNAME}")

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
