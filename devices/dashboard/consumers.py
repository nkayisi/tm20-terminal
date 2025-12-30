"""
Consumer WebSocket pour le dashboard temps réel
Pousse les mises à jour aux clients du dashboard
"""

import asyncio
import json
import logging
from typing import Set

from channels.generic.websocket import AsyncWebsocketConsumer

from ..core.events import EventBus, Event, EventType
from ..core.device_manager import DeviceManager
from ..core.metrics import MetricsCollector

logger = logging.getLogger('devices.dashboard')


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket pour le dashboard
    
    Permet aux clients du dashboard de recevoir
    les mises à jour en temps réel
    """
    
    # Groupe Channels pour broadcast
    DASHBOARD_GROUP = 'dashboard_updates'
    
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
        
        # S'abonner aux événements
        event_bus = EventBus.get_instance()
        event_bus.subscribe_all(self._handle_event)
    
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
    
    async def _handle_event(self, event: Event):
        """Gère un événement du système"""
        # Convertir en message WebSocket
        message = {
            'type': 'event',
            'event_type': event.type.name,
            'data': event.data,
            'timestamp': event.timestamp.isoformat(),
            'source': event.source,
        }
        
        # Envoyer au groupe
        await self.channel_layer.group_send(
            self.DASHBOARD_GROUP,
            {
                'type': 'dashboard_event',
                'message': message
            }
        )
    
    async def dashboard_event(self, event):
        """Handler pour les messages de groupe"""
        await self.send(text_data=json.dumps(event['message']))
    
    async def dashboard_update(self, event):
        """Handler générique pour les mises à jour"""
        await self.send(text_data=json.dumps(event['data']))
