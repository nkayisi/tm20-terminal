"""
Routing WebSocket - terminaux TM20 et dashboard temps réel.

L'ordre compte : la route la plus spécifique d'abord. Le dashboard est le seul
client WebSocket qui n'est pas un terminal, il doit donc être résolu avant le
attrape-tout qui sert les terminaux.
"""

from django.urls import re_path

from .consumers import TM20ConsumerV2
from .dashboard.consumers import DashboardConsumer

websocket_urlpatterns = [
    # Dashboard temps réel (navigateur) — doit passer AVANT l'attrape-tout.
    re_path(r'^ws/dashboard/?$', DashboardConsumer.as_asgi()),

    # Terminaux TM20, chemins connus.
    re_path(r'^ws/tm20/?$', TM20ConsumerV2.as_asgi()),
    re_path(r'^ws/tm20/(?P<sn>\w+)/?$', TM20ConsumerV2.as_asgi()),
    re_path(r'^pub/chat$', TM20ConsumerV2.as_asgi()),
    re_path(r'^$', TM20ConsumerV2.as_asgi()),

    # Attrape-tout terminaux.
    #
    # Le chemin WebSocket n'est pas défini par le protocole (doc section 1 :
    # « transport WebSocket, port 7788 », rien sur l'URL) et il varie d'un
    # firmware à l'autre : /, /pub/chat, /websocket... Un chemin non prévu
    # faisait lever `ValueError: No route found` par Channels, soit une 500
    # opaque côté terminal et une trace illisible côté serveur.
    #
    # Ce serveur n'accueille que des terminaux sur ce port : accepter tout
    # chemin restant est le comportement utile. Le consumer journalise le
    # chemin réellement demandé, ce qui permet de diagnostiquer un firmware
    # inconnu au lieu de le voir échouer en silence.
    re_path(r'^.*$', TM20ConsumerV2.as_asgi()),
]
