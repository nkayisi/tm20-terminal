import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from django.conf import settings
from devices.routing import websocket_urlpatterns

# En mode DEBUG, pas de validation d'origine pour permettre les tests
# et les connexions des terminaux TM20 (qui n'envoient pas d'Origin header)
if settings.DEBUG:
    websocket_app = URLRouter(websocket_urlpatterns)
else:
    from channels.security.websocket import AllowedHostsOriginValidator
    websocket_app = AllowedHostsOriginValidator(
        URLRouter(websocket_urlpatterns)
    )

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': websocket_app,
})
