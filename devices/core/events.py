"""
Système d'événements pour communication temps réel
Permet la notification du dashboard et autres composants
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from weakref import WeakSet

logger = logging.getLogger('devices.events')


class EventType(Enum):
    """Types d'événements du système"""
    
    # Connexion
    DEVICE_CONNECTED = auto()
    DEVICE_DISCONNECTED = auto()
    DEVICE_REGISTERED = auto()
    DEVICE_TIMEOUT = auto()
    
    # Logs
    ATTENDANCE_LOG_RECEIVED = auto()
    ATTENDANCE_LOG_BATCH = auto()
    
    # Utilisateurs
    USER_SYNCED = auto()
    USER_CREATED = auto()
    USER_DELETED = auto()
    
    # Commandes
    COMMAND_SENT = auto()
    COMMAND_RESPONSE = auto()
    COMMAND_TIMEOUT = auto()
    
    # Système
    SERVER_STARTED = auto()
    SERVER_STOPPED = auto()
    ERROR_OCCURRED = auto()
    
    # Métriques
    METRICS_UPDATE = auto()


@dataclass
class Event:
    """Événement système"""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    
    def to_dict(self) -> dict:
        """Convertit l'événement en dictionnaire pour JSON"""
        return {
            'type': self.type.name,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
        }


class EventBus:
    """
    Bus d'événements centralisé (Singleton)
    Permet la communication découplée entre composants
    """
    
    _instance: Optional['EventBus'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._global_subscribers: List[Callable] = []
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._history: List[Event] = []
        self._max_history = 1000
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'EventBus':
        """Récupère l'instance singleton"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], Coroutine]
    ) -> None:
        """Abonne un handler à un type d'événement"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.name}")
    
    def subscribe_all(self, handler: Callable[[Event], Coroutine]) -> None:
        """Abonne un handler à tous les événements"""
        self._global_subscribers.append(handler)
        logger.debug("Global handler subscribed")
    
    def unsubscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], Coroutine]
    ) -> None:
        """Désabonne un handler"""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
    
    async def publish(self, event: Event) -> None:
        """Publie un événement (async)"""
        await self._event_queue.put(event)
        
        # Garder l'historique
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
    
    def publish_sync(self, event: Event) -> None:
        """Publie un événement (sync) - utilise asyncio.create_task si possible"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # Pas de loop en cours, on stocke directement
            self._history.append(event)
    
    async def emit(
        self,
        event_type: EventType,
        data: Dict[str, Any] = None,
        source: str = ""
    ) -> None:
        """Raccourci pour créer et publier un événement"""
        event = Event(
            type=event_type,
            data=data or {},
            source=source
        )
        await self.publish(event)
    
    async def start(self) -> None:
        """Démarre le processeur d'événements"""
        if self._running:
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("EventBus started")
    
    async def stop(self) -> None:
        """Arrête le processeur d'événements"""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus stopped")
    
    async def _process_events(self) -> None:
        """Boucle de traitement des événements"""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error processing event: {e}")
    
    async def _dispatch(self, event: Event) -> None:
        """Dispatch un événement aux handlers"""
        handlers = []
        
        # Handlers spécifiques
        if event.type in self._subscribers:
            handlers.extend(self._subscribers[event.type])
        
        # Handlers globaux
        handlers.extend(self._global_subscribers)
        
        # Exécuter tous les handlers en parallèle
        if handlers:
            tasks = [
                asyncio.create_task(self._safe_call(handler, event))
                for handler in handlers
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_call(
        self,
        handler: Callable[[Event], Coroutine],
        event: Event
    ) -> None:
        """Appelle un handler de manière sécurisée"""
        try:
            await handler(event)
        except Exception as e:
            logger.exception(f"Handler error for {event.type.name}: {e}")
    
    def get_recent_events(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[Event]:
        """Récupère les événements récents"""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]
    
    @property
    def stats(self) -> dict:
        """Statistiques du bus d'événements"""
        return {
            'running': self._running,
            'queue_size': self._event_queue.qsize(),
            'history_size': len(self._history),
            'subscribers': {
                et.name: len(handlers)
                for et, handlers in self._subscribers.items()
            },
            'global_subscribers': len(self._global_subscribers),
        }


# Instance globale
event_bus = EventBus.get_instance()
