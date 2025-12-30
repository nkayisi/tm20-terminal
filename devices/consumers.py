"""
Consumer WebSocket v2 - Architecture refactorée
Léger, découplé, optimisé pour haute charge

Responsabilités :
- Transport WebSocket uniquement
- Délégation aux handlers
- Intégration Device Manager
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Optional

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .models import Terminal
from .protocol import TM20Parser, MessageValidator, ValidationError
from .handlers import (
    RegistrationHandler,
    AttendanceHandler,
    UserHandler,
    QRCodeHandler,
    ResponseHandler,
    HandlerResult,
)
from .core.device_manager import DeviceManager, DeviceState
from .core.events import EventBus, EventType
from .core.metrics import MetricsCollector
from .services.commands import CommandService

logger = logging.getLogger('devices.consumer')


class TM20ConsumerV2(AsyncWebsocketConsumer):
    """
    Consumer WebSocket v2 pour terminaux TM20
    
    Architecture :
    - Consumer léger (transport uniquement)
    - Handlers spécialisés par type de message
    - Device Manager centralisé
    - Métriques intégrées
    """
    
    # Handlers (partagés entre instances)
    _handlers: Dict[str, object] = {}
    _handlers_initialized = False
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.sn: Optional[str] = None
        self.terminal: Optional[Terminal] = None
        self.registered: bool = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.last_message_at: datetime = datetime.now()
        
        # Singletons
        self._device_manager = DeviceManager.get_instance()
        self._event_bus = EventBus.get_instance()
        self._metrics = MetricsCollector.get_instance()
        self._command_service = CommandService()
        
        # Initialiser les handlers (une seule fois)
        self._init_handlers()
    
    @classmethod
    def _init_handlers(cls):
        """Initialise les handlers (partagés)"""
        if cls._handlers_initialized:
            return
        
        cls._handlers = {
            'reg': RegistrationHandler(),
            'sendlog': AttendanceHandler(),
            'senduser': UserHandler(),
            'sendqrcode': QRCodeHandler(),
        }
        cls._response_handler = ResponseHandler()
        cls._handlers_initialized = True
    
    async def connect(self):
        """Connexion WebSocket établie"""
        await self.accept()
        
        client = self.scope.get('client', ('unknown', 0))
        logger.info(f"WebSocket connected: {client[0]}:{client[1]}")
        
        # Démarrer le heartbeat
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Événement
        await self._event_bus.emit(
            EventType.DEVICE_CONNECTED,
            {'client': f"{client[0]}:{client[1]}"},
            source='TM20Consumer'
        )
    
    async def disconnect(self, close_code):
        """Déconnexion WebSocket"""
        logger.info(f"WebSocket disconnected: {self.sn or 'unregistered'} (code: {close_code})")
        
        # Arrêter le heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Désenregistrer du Device Manager
        if self.sn:
            await self._device_manager.unregister(self.sn)
            
            # Mettre à jour le statut en DB
            from .services.registration import RegistrationService
            await RegistrationService().update_status(self.sn, is_active=False)
        
        # Mettre à jour les métriques
        self._metrics.update_active_connections(
            len(await self._device_manager.get_connected_sns())
        )
    
    async def receive(self, text_data=None, bytes_data=None):
        """Message reçu du terminal"""
        start_time = time.perf_counter()
        self.last_message_at = datetime.now()
        
        data = text_data or bytes_data
        if not data:
            return
        
        try:
            # Parser le JSON
            message = TM20Parser.parse_json(data)
            
            # Valider le message
            try:
                MessageValidator.validate(message)
            except ValidationError as e:
                logger.warning(f"Invalid message: {e.message}")
                return
            
            # Traiter le message
            await self._dispatch(message)
            
            # Métriques
            elapsed = time.perf_counter() - start_time
            self._metrics.record_message(self.sn or 'unknown', 'received')
            self._metrics.record_latency('message', elapsed)
            
            # Toucher le Device Manager
            if self.sn:
                await self._device_manager.touch(self.sn)
            
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
    
    async def _dispatch(self, message: dict):
        """Dispatch le message vers le bon handler"""
        cmd = message.get('cmd', '').lower()
        ret = message.get('ret', '').lower()
        
        if cmd:
            await self._handle_command(cmd, message)
        elif ret:
            await self._handle_response(ret, message)
        else:
            logger.warning(f"Unknown message type: {message.keys()}")
    
    async def _handle_command(self, cmd: str, message: dict):
        """Traite une commande du terminal"""
        handler = self._handlers.get(cmd)
        
        if not handler:
            logger.warning(f"No handler for command: {cmd}")
            return
        
        # Exécuter le handler
        result: HandlerResult = await handler.handle(
            message,
            terminal=self.terminal,
            sn=self.sn
        )
        
        # Actions post-handler pour reg
        if cmd == 'reg' and result.success:
            self.sn = result.data.get('sn')
            self.terminal = result.data.get('terminal')
            self.registered = True
            
            # Enregistrer dans le Device Manager
            await self._device_manager.register(
                self.sn,
                self,
                metadata={
                    'model': self.terminal.model if self.terminal else '',
                    'firmware': self.terminal.firmware if self.terminal else '',
                }
            )
            
            # Mettre à jour les métriques
            self._metrics.update_active_connections(
                len(await self._device_manager.get_connected_sns())
            )
            
            # Envoyer les commandes en attente
            await self._send_pending_commands()
        
        # Envoyer la réponse
        if result.response:
            await self._send_json(result.response)
    
    async def _handle_response(self, ret: str, message: dict):
        """Traite une réponse du terminal"""
        result = await self._response_handler.handle(
            message,
            terminal=self.terminal,
            sn=self.sn
        )
        # Les réponses n'ont pas de réponse à envoyer
    
    async def _send_pending_commands(self):
        """Envoie les commandes en attente"""
        if not self.terminal:
            return
        
        commands = await self._command_service.get_pending(self.terminal)
        
        for cmd in commands:
            try:
                await self._send_json(cmd.payload)
                await self._command_service.mark_sent(cmd.id)
                logger.info(f"[{self.sn}] Command sent: {cmd.command}")
            except Exception as e:
                logger.error(f"Error sending command {cmd.id}: {e}")
    
    async def _heartbeat_loop(self):
        """Boucle de vérification du heartbeat"""
        timeout = settings.TM20_SETTINGS.get('CONNECTION_TIMEOUT', 120)
        interval = settings.TM20_SETTINGS.get('HEARTBEAT_INTERVAL', 30)
        
        while True:
            try:
                await asyncio.sleep(interval)
                
                elapsed = (datetime.now() - self.last_message_at).total_seconds()
                if elapsed > timeout:
                    logger.warning(f"[{self.sn}] Timeout, closing connection")
                    await self._event_bus.emit(
                        EventType.DEVICE_TIMEOUT,
                        {'sn': self.sn},
                        source='TM20Consumer'
                    )
                    await self.close()
                    break
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _send_json(self, data: dict):
        """Envoie un message JSON au terminal"""
        message = TM20Parser.serialize(data)
        await self.send(text_data=message)
        
        self._metrics.record_message(self.sn or 'unknown', 'sent')
        logger.debug(f"[{self.sn}] Sent: {message[:200]}")
    
    # === API publique pour envoi de commandes ===
    
    async def send_command(self, command: dict) -> bool:
        """Envoie une commande au terminal"""
        try:
            await self._send_json(command)
            return True
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return False
