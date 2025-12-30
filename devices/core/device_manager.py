"""
Device Manager - Gestionnaire centralisé des connexions terminaux
Thread-safe, async-first, optimisé pour 100+ devices
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from django.conf import settings
from django.utils import timezone
from django.core.cache import cache

from .events import EventBus, Event, EventType

if TYPE_CHECKING:
    from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger('devices.manager')


class DeviceState(Enum):
    """États possibles d'un terminal"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    REGISTERED = auto()
    ONLINE = auto()
    OFFLINE = auto()
    ERROR = auto()


@dataclass
class DeviceConnection:
    """Représente une connexion active à un terminal"""
    sn: str
    consumer: 'AsyncWebsocketConsumer'
    state: DeviceState = DeviceState.CONNECTED
    connected_at: datetime = field(default_factory=datetime.now)
    last_message_at: datetime = field(default_factory=datetime.now)
    last_heartbeat_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    error_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def uptime(self) -> timedelta:
        """Durée de connexion"""
        return datetime.now() - self.connected_at
    
    @property
    def is_healthy(self) -> bool:
        """Vérifie si la connexion est saine"""
        timeout = settings.TM20_SETTINGS.get('CONNECTION_TIMEOUT', 120)
        elapsed = (datetime.now() - self.last_message_at).total_seconds()
        return elapsed < timeout and self.error_count < 5
    
    def touch(self) -> None:
        """Met à jour le timestamp du dernier message"""
        self.last_message_at = datetime.now()
        self.message_count += 1
    
    def record_error(self) -> None:
        """Enregistre une erreur"""
        self.error_count += 1
    
    def to_dict(self) -> dict:
        """Sérialise pour JSON"""
        return {
            'sn': self.sn,
            'state': self.state.name,
            'connected_at': self.connected_at.isoformat(),
            'last_message_at': self.last_message_at.isoformat(),
            'uptime_seconds': self.uptime.total_seconds(),
            'message_count': self.message_count,
            'error_count': self.error_count,
            'is_healthy': self.is_healthy,
            'metadata': self.metadata,
        }


class DeviceManager:
    """
    Gestionnaire centralisé des connexions aux terminaux
    
    Fonctionnalités :
    - Pool de connexions thread-safe
    - Heartbeat monitoring
    - Envoi de commandes ciblées ou broadcast
    - Métriques et statistiques
    - Intégration EventBus pour temps réel
    """
    
    _instance: Optional['DeviceManager'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._connections: Dict[str, DeviceConnection] = {}
        self._conn_lock = asyncio.Lock()
        self._event_bus = EventBus.get_instance()
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Métriques
        self._total_connections = 0
        self._total_disconnections = 0
        self._total_messages = 0
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'DeviceManager':
        """Récupère l'instance singleton"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def start(self) -> None:
        """Démarre le manager et le monitoring"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._health_monitor())
        logger.info("DeviceManager started")
        
        await self._event_bus.emit(
            EventType.SERVER_STARTED,
            {'manager': 'DeviceManager'}
        )
    
    async def stop(self) -> None:
        """Arrête le manager"""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        # Fermer toutes les connexions
        async with self._conn_lock:
            for conn in list(self._connections.values()):
                try:
                    await conn.consumer.close()
                except Exception:
                    pass
            self._connections.clear()
        
        logger.info("DeviceManager stopped")
    
    async def register(
        self,
        sn: str,
        consumer: 'AsyncWebsocketConsumer',
        metadata: Dict[str, Any] = None
    ) -> DeviceConnection:
        """
        Enregistre une nouvelle connexion
        Si le SN existe déjà, ferme l'ancienne connexion
        """
        async with self._conn_lock:
            # Fermer l'ancienne connexion si elle existe
            if sn in self._connections:
                old_conn = self._connections[sn]
                logger.warning(f"Replacing existing connection for {sn}")
                try:
                    await old_conn.consumer.close()
                except Exception:
                    pass
                self._total_disconnections += 1
            
            # Créer la nouvelle connexion
            connection = DeviceConnection(
                sn=sn,
                consumer=consumer,
                state=DeviceState.REGISTERED,
                metadata=metadata or {}
            )
            self._connections[sn] = connection
            self._total_connections += 1
            
            logger.info(f"Device registered: {sn} (total: {len(self._connections)})")
            
            # Stocker dans Redis pour partage inter-processus
            self._update_redis_connections()
        
        # Émettre l'événement
        await self._event_bus.emit(
            EventType.DEVICE_REGISTERED,
            {
                'sn': sn,
                'total_connected': len(self._connections),
                'metadata': metadata,
            },
            source='DeviceManager'
        )
        
        return connection
    
    async def unregister(self, sn: str) -> bool:
        """Désenregistre une connexion"""
        async with self._conn_lock:
            if sn not in self._connections:
                return False
            
            conn = self._connections.pop(sn)
            self._total_disconnections += 1
            
            logger.info(f"Device unregistered: {sn} (total: {len(self._connections)})")
            
            # Mettre à jour Redis
            self._update_redis_connections()
        
        # Émettre l'événement
        await self._event_bus.emit(
            EventType.DEVICE_DISCONNECTED,
            {
                'sn': sn,
                'uptime_seconds': conn.uptime.total_seconds(),
                'message_count': conn.message_count,
                'total_connected': len(self._connections),
            },
            source='DeviceManager'
        )
        
        return True
    
    async def get_connection(self, sn: str) -> Optional[DeviceConnection]:
        """Récupère une connexion par SN"""
        async with self._conn_lock:
            return self._connections.get(sn)
    
    async def get_all_connections(self) -> List[DeviceConnection]:
        """Récupère toutes les connexions"""
        async with self._conn_lock:
            return list(self._connections.values())
    
    async def get_connected_sns(self) -> List[str]:
        """Liste des SN connectés"""
        async with self._conn_lock:
            return list(self._connections.keys())
    
    async def is_connected(self, sn: str) -> bool:
        """Vérifie si un terminal est connecté"""
        async with self._conn_lock:
            return sn in self._connections
    
    async def touch(self, sn: str) -> None:
        """Met à jour le timestamp du dernier message"""
        async with self._conn_lock:
            if sn in self._connections:
                self._connections[sn].touch()
                self._total_messages += 1
    
    async def update_state(self, sn: str, state: DeviceState) -> None:
        """Met à jour l'état d'un terminal"""
        async with self._conn_lock:
            if sn in self._connections:
                self._connections[sn].state = state
    
    async def send_to_device(
        self,
        sn: str,
        message: dict,
        timeout: float = 10.0
    ) -> bool:
        """
        Envoie un message à un terminal spécifique
        Retourne True si envoyé avec succès
        """
        conn = await self.get_connection(sn)
        if not conn:
            logger.warning(f"Cannot send to {sn}: not connected")
            return False
        
        try:
            import orjson
            data = orjson.dumps(message).decode()
            await asyncio.wait_for(
                conn.consumer.send(text_data=data),
                timeout=timeout
            )
            
            await self._event_bus.emit(
                EventType.COMMAND_SENT,
                {'sn': sn, 'command': message.get('cmd', 'unknown')},
                source='DeviceManager'
            )
            
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout sending to {sn}")
            conn.record_error()
            return False
        except Exception as e:
            logger.exception(f"Error sending to {sn}: {e}")
            conn.record_error()
            return False
    
    async def broadcast(
        self,
        message: dict,
        filter_fn: Callable[[DeviceConnection], bool] = None
    ) -> Dict[str, bool]:
        """
        Broadcast un message à tous les terminaux (ou filtrés)
        Retourne un dict {sn: success}
        """
        connections = await self.get_all_connections()
        
        if filter_fn:
            connections = [c for c in connections if filter_fn(c)]
        
        results = {}
        tasks = []
        
        for conn in connections:
            task = asyncio.create_task(
                self.send_to_device(conn.sn, message)
            )
            tasks.append((conn.sn, task))
        
        for sn, task in tasks:
            try:
                results[sn] = await task
            except Exception:
                results[sn] = False
        
        return results
    
    async def _health_monitor(self) -> None:
        """
        Boucle de monitoring de la santé des connexions
        Détecte les timeouts et connexions mortes
        """
        interval = settings.TM20_SETTINGS.get('HEARTBEAT_INTERVAL', 30)
        timeout = settings.TM20_SETTINGS.get('CONNECTION_TIMEOUT', 120)
        
        while self._running:
            try:
                await asyncio.sleep(interval)
                
                now = datetime.now()
                unhealthy = []
                
                async with self._conn_lock:
                    for sn, conn in list(self._connections.items()):
                        elapsed = (now - conn.last_message_at).total_seconds()
                        
                        if elapsed > timeout:
                            unhealthy.append(sn)
                            conn.state = DeviceState.OFFLINE
                
                # Émettre les événements de timeout
                for sn in unhealthy:
                    await self._event_bus.emit(
                        EventType.DEVICE_TIMEOUT,
                        {'sn': sn},
                        source='DeviceManager.health_monitor'
                    )
                    logger.warning(f"Device timeout: {sn}")
                
                # Émettre les métriques périodiques
                await self._event_bus.emit(
                    EventType.METRICS_UPDATE,
                    self.stats,
                    source='DeviceManager'
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Health monitor error: {e}")
    
    @property
    def stats(self) -> dict:
        """Statistiques du manager"""
        connections = list(self._connections.values())
        healthy = sum(1 for c in connections if c.is_healthy)
        
        return {
            'connected': len(connections),
            'healthy': healthy,
            'unhealthy': len(connections) - healthy,
            'total_connections': self._total_connections,
            'total_disconnections': self._total_disconnections,
            'total_messages': self._total_messages,
            'running': self._running,
        }
    
    def get_stats_sync(self) -> dict:
        """Version synchrone des stats (pour admin Django)"""
        return self.stats
    
    async def get_devices_status(self) -> List[dict]:
        """Liste complète des terminaux avec leur statut"""
        connections = await self.get_all_connections()
        return [conn.to_dict() for conn in connections]
    
    def _update_redis_connections(self) -> None:
        """Met à jour la liste des connexions dans Redis (sync)"""
        try:
            connected_sns = list(self._connections.keys())
            cache.set('tm20:connected_devices', connected_sns, timeout=120)
            cache.set('tm20:connected_count', len(connected_sns), timeout=120)
        except Exception as e:
            logger.error(f"Error updating Redis connections: {e}")
    
    @staticmethod
    def get_connected_count_from_redis() -> int:
        """Récupère le nombre de connexions depuis Redis (pour django-http)"""
        try:
            count = cache.get('tm20:connected_count', 0)
            return count if count is not None else 0
        except Exception as e:
            logger.error(f"Error reading Redis connections: {e}")
            return 0
    
    @staticmethod
    def get_connected_sns_from_redis() -> List[str]:
        """Récupère la liste des SN connectés depuis Redis (pour django-http)"""
        try:
            sns = cache.get('tm20:connected_devices', [])
            return sns if sns is not None else []
        except Exception as e:
            logger.error(f"Error reading Redis connections: {e}")
            return []


# Instance globale
device_manager = DeviceManager.get_instance()
