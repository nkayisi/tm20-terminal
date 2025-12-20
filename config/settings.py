import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')

DEBUG = os.getenv('DEBUG', '0') == '1'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,django.tm20-server.orb.local').split(',')

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
DATABASE_URL = os.getenv('DATABASE_URL', 'postgres://tm20_user:tm20_password@localhost:5432/tm20_db')

if DATABASE_URL:
    import re
    match = re.match(r'postgres://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
    if match:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': match.group(5),
                'USER': match.group(1),
                'PASSWORD': match.group(2),
                'HOST': match.group(3),
                'PORT': match.group(4),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

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

# TM20 Protocol Settings
TM20_SETTINGS = {
    'WEBSOCKET_PORT': int(os.getenv('TM20_WEBSOCKET_PORT', 7788)),
    'HEARTBEAT_INTERVAL': int(os.getenv('TM20_HEARTBEAT_INTERVAL', 30)),
    'CONNECTION_TIMEOUT': int(os.getenv('TM20_CONNECTION_TIMEOUT', 120)),
    'MAX_LOG_BATCH_SIZE': 40,
    'REQUIRE_WHITELIST': os.getenv('TM20_REQUIRE_WHITELIST', '0') == '1',
}

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'tm20': {
            'format': '[{asctime}] [{levelname}] [TM20] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'tm20_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'tm20.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'tm20',
        },
    },
    'loggers': {
    'django': {
        'handlers': ['console'],
        'level': 'INFO',
    },

    # 🔥 CRUCIAL POUR WEBSOCKET
    'django.channels': {
        'handlers': ['console'],
        'level': 'DEBUG',
        'propagate': False,
    },
    'channels.server': {
        'handlers': ['console'],
        'level': 'DEBUG',
        'propagate': False,
    },

    # Ton logger TM20
    'devices': {
        'handlers': ['console', 'tm20_file'],
        'level': 'DEBUG',
        'propagate': False,
    },
},
}

# Create logs directory
(BASE_DIR / 'logs').mkdir(exist_ok=True)

CORS_ALLOW_ALL_ORIGINS = DEBUG
