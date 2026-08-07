import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: str = '0') -> bool:
    """Lit une variable d'environnement booléenne (1/true/yes/on)."""
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


DEBUG = env_bool('DEBUG', '0')

# Clé secrète : un fallback n'est toléré qu'en mode DEBUG.
# En production (DEBUG=0), l'absence de DJANGO_SECRET_KEY doit stopper le démarrage.
_DEV_SECRET_KEY = 'dev-secret-key-change-in-production'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = _DEV_SECRET_KEY
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY est obligatoire lorsque DEBUG=0. "
            "Définissez une clé secrète unique dans l'environnement."
        )

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()
]

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'corsheaders',
    'devices',
    'django_celery_beat',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database PostgreSQL
# Supporte postgres:// ET postgresql:// (Render utilise postgresql://)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgres://tm20_user:tm20_password@localhost:5432/tm20_db')


def _sqlite_config():
    return {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


def _postgres_config(url: str):
    """Parse une URL PostgreSQL de façon robuste.

    Gère les mots de passe contenant des caractères spéciaux (@, :, /),
    l'absence de port explicite, et les paramètres de query (ex: sslmode).
    """
    from urllib.parse import urlparse, unquote, parse_qs

    parsed = urlparse(url)
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname:
        return None

    options = {'connect_timeout': 10}
    sslmode = parse_qs(parsed.query).get('sslmode')
    if sslmode:
        options['sslmode'] = sslmode[0]

    return {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': unquote(parsed.path.lstrip('/')),
            'USER': unquote(parsed.username or ''),
            'PASSWORD': unquote(parsed.password or ''),
            'HOST': parsed.hostname,
            'PORT': str(parsed.port or 5432),
            'CONN_MAX_AGE': 600,  # Connection pooling
            'OPTIONS': options,
        }
    }


DATABASES = (DATABASE_URL and _postgres_config(DATABASE_URL)) or _sqlite_config()

# Redis Channel Layer
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
            'capacity': 1500,
            'expiry': 10,
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise configuration
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cache Configuration (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://redis:6379/0'),
        'KEY_PREFIX': 'tm20',
        'TIMEOUT': 300,
    }
}

# TM20 Protocol Settings
TM20_SETTINGS = {
    'WEBSOCKET_PORT': int(os.getenv('TM20_WEBSOCKET_PORT', 7788)),
    'HEARTBEAT_INTERVAL': int(os.getenv('TM20_HEARTBEAT_INTERVAL', 30)),
    'CONNECTION_TIMEOUT': int(os.getenv('TM20_CONNECTION_TIMEOUT', 120)),
    'MAX_LOG_BATCH_SIZE': 40,
    'REQUIRE_WHITELIST': env_bool('TM20_REQUIRE_WHITELIST', '0'),
    # Fuseau dans lequel les terminaux expriment l'heure murale.
    # Vide => on utilise TIME_ZONE (UTC). Ex: 'Africa/Kigali' pour un site UTC+2.
    'TERMINAL_TIMEZONE': os.getenv('TM20_TERMINAL_TIMEZONE', '') or TIME_ZONE,
}

LOG_DIR = Path(os.environ.get("LOG_DIR", "/tmp/logs"))

# On tente de préparer un fichier de log. Si le dossier n'est pas accessible en
# écriture (ex: conteneur non-root, dossier appartenant à root, volume monté en
# lecture seule), on retombe sur le logging console uniquement plutôt que de
# faire échouer le démarrage de tous les services.
_log_file = None
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _probe = LOG_DIR / ".write_test"
    _probe.touch()
    _probe.unlink()
    _log_file = str(LOG_DIR / "tm20.log")
except OSError:
    _log_file = None

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# On n'ajoute le handler fichier que si le dossier de logs est réellement
# accessible en écriture.
if _log_file:
    LOGGING["handlers"]["tm20_file"] = {
        "level": "INFO",
        "class": "logging.handlers.RotatingFileHandler",
        "filename": _log_file,
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 3,
        "formatter": "verbose",
    }
    LOGGING["root"]["handlers"].append("tm20_file")


# Create logs directory
# (BASE_DIR / 'logs').mkdir(exist_ok=True)

CORS_ALLOW_ALL_ORIGINS = DEBUG

# Celery Configuration
CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Authentication settings
LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

# Cookies sécurisés : activés par défaut en production (DEBUG=0),
# désactivables via SECURE_COOKIES pour le dev en HTTP.
SECURE_COOKIES = env_bool('SECURE_COOKIES', '0' if DEBUG else '1')

# Session Configuration (Redis pour partage entre services)
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24 heures
SESSION_COOKIE_SECURE = SECURE_COOKIES  # True en HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF Configuration
CSRF_COOKIE_SECURE = SECURE_COOKIES  # True en HTTPS
CSRF_COOKIE_HTTPONLY = False  # Doit être False pour JS
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000').split(',')
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'
