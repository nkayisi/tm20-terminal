"""
Consumer WebSocket pour le dashboard temps réel
Pousse les mises à jour aux clients du dashboard
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer

from ..core.events import EventBus, Event
from ..core.device_manager import DeviceManager
from ..core.metrics import MetricsCollector

logger = logging.getLogger('devices.dashboard')

# Groupe Channels de diffusion du dashboard.
DASHBOARD_GROUP = 'dashboard_updates'

# Un SEUL abonne au bus pour tout le process.
#
# Abonner `self._handle_event` par connexion faisait diffuser chaque
# evenement une fois par abonne, et chaque diffusion touchait tous les
# membres du groupe : K dashboards ouverts => K x K trames par evenement
# (flux d'activite duplique, `scheduleRefresh()` declenche autant de fois).
# Le desabonnement au `disconnect` reglait les handlers morts, pas cette
# duplication entre connexions vivantes.
_broadcast_subscribed = False


async def _broadcast_event(event: Event) -> None:
    """Relaie un evenement du bus vers le groupe dashboard, une seule fois."""
    layer = get_channel_layer()
    if layer is None:
        return

    await layer.group_send(
        DASHBOARD_GROUP,
        {
            'type': 'dashboard_event',
            'message': {
                'type': 'event',
                'event_type': event.type.name,
                'data': event.data,
                'timestamp': event.timestamp.isoformat(),
                'source': event.source,
            },
        },
    )


def _ensure_broadcast_subscription() -> None:
    """Abonne le relais au bus au premier dashboard connecte.

    Jamais desabonne : c'est une fonction de module, pas un objet a duree de
    vie courte, donc aucune fuite. Sans dashboard connecte, le `group_send`
    n'a simplement aucun destinataire.
    """
    global _broadcast_subscribed
    if _broadcast_subscribed:
        return

    EventBus.get_instance().subscribe_all(_broadcast_event)
    _broadcast_subscribed = True
    logger.info("Relais EventBus -> dashboard abonne (une fois par process)")


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket pour le dashboard
    
    Permet aux clients du dashboard de recevoir
    les mises à jour en temps réel
    """
    
    # Groupe Channels pour broadcast (alias du constant de module).
    DASHBOARD_GROUP = DASHBOARD_GROUP

    async def connect(self):
        """Connexion d'un client dashboard"""
        await self.channel_layer.group_add(
            self.DASHBOARD_GROUP,
            self.channel_name
        )
        await self.accept()

        logger.info(f"Dashboard client connected: {self.channel_name}")

        # Envoyer l'état initial
        await self._send_initial_state()

        # La diffusion des evenements passe par un relais unique au niveau
        # module : rien n'est abonne par connexion (cf. _broadcast_event).
        _ensure_broadcast_subscription()

    async def disconnect(self, close_code):
        """Déconnexion d'un client dashboard"""
        await self.channel_layer.group_discard(
            self.DASHBOARD_GROUP,
            self.channel_name
        )
        logger.info(f"Dashboard client disconnected: {self.channel_name}")
    
    async def receive(self, text_data=None, bytes_data=None):
        """Message reçu du client dashboard"""
        if not text_data:
            return
        
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            
            elif action == 'get_metrics':
                await self._send_metrics()
            
            elif action == 'get_terminals':
                await self._send_terminals()
            
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from dashboard client")
    
    async def _send_initial_state(self):
        """Envoie l'état initial au client"""
        await self._send_metrics()
        await self._send_terminals()
    
    async def _send_metrics(self):
        """Envoie les métriques actuelles"""
        metrics = MetricsCollector.get_instance()
        
        await self.send(text_data=json.dumps({
            'type': 'metrics',
            'data': metrics.get_all_stats()
        }))
    
    async def _send_terminals(self):
        """Envoie la liste des terminaux"""
        device_manager = DeviceManager.get_instance()
        devices = await device_manager.get_devices_status()
        
        await self.send(text_data=json.dumps({
            'type': 'terminals',
            'data': devices
        }))
    
    async def dashboard_event(self, event):
        """Handler pour les messages de groupe"""
        await self.send(text_data=json.dumps(event['message']))
    
    async def dashboard_update(self, event):
        """Handler générique pour les mises à jour"""
        await self.send(text_data=json.dumps(event['data']))
