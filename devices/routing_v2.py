"""
Routing WebSocket v2 - Architecture refactorée
Inclut le routing pour les terminaux TM20 et le dashboard
"""

from django.urls import re_path

from .consumers import TM20ConsumerV2
from .dashboard.consumers import DashboardConsumer

websocket_urlpatterns = [
    # Terminal TM20 endpoints
    re_path(r'^ws/tm20/?$', TM20ConsumerV2.as_asgi()),
    re_path(r'^ws/tm20/(?P<sn>\w+)/?$', TM20ConsumerV2.as_asgi()),
    
    # Legacy endpoints (compatibilité)
    re_path(r'^pub/chat$', TM20ConsumerV2.as_asgi()),
    re_path(r'^$', TM20ConsumerV2.as_asgi()),
    
    # Dashboard WebSocket
    re_path(r'^ws/dashboard/?$', DashboardConsumer.as_asgi()),
]
