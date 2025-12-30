"""
Routing WebSocket pour les terminaux TM20
"""

from django.urls import re_path

from .consumers import TM20Consumer

websocket_urlpatterns = [
    re_path(r"^pub/chat$", TM20Consumer.as_asgi()), 
    re_path(r'^$', TM20Consumer.as_asgi()), 
    re_path(r'^ws/tm20/?$', TM20Consumer.as_asgi()),
    re_path(r'^ws/tm20/(?P<sn>\w+)/?$', TM20Consumer.as_asgi()),
]
