# config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Explicit path, so .env is found no matter which directory the server starts in
load_dotenv(BASE_DIR / ".env")

# ============ الأمان ============
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]
# Full origins with scheme, e.g. https://clinic.example.com (needed for HTTPS form posts)
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

if not DEBUG:
    if not SECRET_KEY:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("SECRET_KEY must be set in .env when DEBUG is off.")

    # The host (e.g. PythonAnywhere) terminates HTTPS in front of Django and says so
    # in X-Forwarded-Proto, so request.is_secure() and absolute links use https
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # On PythonAnywhere, turn on "Force HTTPS" in the Web tab instead of this
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False") == "True"
    SESSION_COOKIE_SECURE = os.getenv("SECURE_COOKIES", "True") == "True"
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    # Raise (e.g. to 31536000) once HTTPS is confirmed working; browsers remember it
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

# ============ التطبيقات ============
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # تطبيقاتنا
    "tenants",
    "accounts",
    "appointments",
    "patients",
    "billing",
    "notifications",
    "dashboard",
]
# config/settings.py

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",   
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "tenants.middleware.CurrentClinicMiddleware",
]

# ============ اللغة والتوقيت ============
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Hebron"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("ar", "العربية"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            # {% icon %}, |status_badge and |initials in every template without {% load %}
            "builtins": ["dashboard.templatetags.ui"],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",  
                "tenants.context_processors.current_clinic",
                "accounts.context_processors.current_staff_user",
                "notifications.context_processors.unread_notifications_count",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ============ قاعدة البيانات ============
# DB_ENGINE=sqlite uses a db.sqlite3 file in the project folder (e.g. on PythonAnywhere's
# free tier). Anything else, including leaving it unset, uses MySQL from the DB_* settings.
if os.getenv("DB_ENGINE", "mysql").lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                # Strict mode makes MySQL reject bad data instead of silently truncating it
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

# ============ التحقق من كلمات السر ============
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============ الملفات الثابتة والميديا ============
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============ Stripe ============
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# ============ Email ============
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
# SMTP (Gmail: smtp.gmail.com, port 587, TLS, and a Google App Password)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 15
# Verification emails ask for a "YES" reply, read back from this inbox over IMAP.
# Set EMAIL_VERIFY_BY_REPLY=False where IMAP is blocked (PythonAnywhere free accounts):
# verification emails then carry a link instead.
EMAIL_IMAP_HOST = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
EMAIL_VERIFY_BY_REPLY = os.getenv("EMAIL_VERIFY_BY_REPLY", "True") == "True"
# Gmail sends as the account address anyway, so default the sender to it
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER or "noreply@clinicsaas.local"

# ============ Logging ============
# Errors and warnings go to stderr; under systemd that's `journalctl -u clinic-saas`
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "WARNING")},
}