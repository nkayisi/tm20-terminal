"""
ASGI Configuration - Production Ready
Architecture unifiée HTTP + WebSocket sur port unique (7788)

Compatible Render.com avec:
- Gunicorn + UvicornWorker
- HTTP et WebSocket sur le même port
- Scalable pour 100+ terminaux biométriques
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# IMPORTANT: Initialiser Django AVANT d'importer les apps
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from django.conf import settings

# Application Django HTTP (doit être créée APRÈS django.setup())
django_asgi_app = get_asgi_application()

# Import des routes WebSocket
from devices.routing import websocket_urlpatterns

# Configuration WebSocket SANS validation d'origine
# Les terminaux TM20 n'envoient pas d'en-tête Origin (RFC6455 autorise cela)
# AllowedHostsOriginValidator bloquerait les connexions des terminaux
websocket_app = URLRouter(websocket_urlpatterns)

# ProtocolTypeRouter: Routage par protocole
# - 'http' → Django classique (admin, API REST, dashboard)
# - 'websocket' → Channels (terminaux TM20, dashboard temps réel)
application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': websocket_app,
})

# Pourquoi cette architecture?
# 1. Un seul serveur ASGI gère HTTP + WebSocket
# 2. Compatible avec Gunicorn + UvicornWorker (production)
# 3. Scalable horizontalement (plusieurs workers)
# 4. Redis comme channel layer pour communication inter-workers
