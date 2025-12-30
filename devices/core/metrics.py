"""
Collecteur de métriques pour monitoring et dashboard
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger('devices.metrics')


@dataclass
class MetricPoint:
    """Point de métrique avec timestamp"""
    value: float
    timestamp: datetime = field(default_factory=datetime.now)


class Counter:
    """Compteur incrémental thread-safe"""
    
    def __init__(self, name: str):
        self.name = name
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self, value: int = 1) -> int:
        async with self._lock:
            self._value += value
            return self._value
    
    def increment_sync(self, value: int = 1) -> int:
        self._value += value
        return self._value
    
    @property
    def value(self) -> int:
        return self._value
    
    def reset(self) -> int:
        old_value = self._value
        self._value = 0
        return old_value


class Gauge:
    """Jauge pour valeurs instantanées"""
    
    def __init__(self, name: str):
        self.name = name
        self._value = 0.0
        self._lock = asyncio.Lock()
    
    async def set(self, value: float) -> None:
        async with self._lock:
            self._value = value
    
    def set_sync(self, value: float) -> None:
        self._value = value
    
    @property
    def value(self) -> float:
        return self._value


class Histogram:
    """Histogramme pour distribution de valeurs"""
    
    def __init__(self, name: str, buckets: List[float] = None):
        self.name = name
        self.buckets = buckets or [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._values: List[float] = []
        self._lock = asyncio.Lock()
        self._max_samples = 10000
    
    async def observe(self, value: float) -> None:
        async with self._lock:
            self._values.append(value)
            if len(self._values) > self._max_samples:
                self._values = self._values[-self._max_samples:]
    
    def observe_sync(self, value: float) -> None:
        self._values.append(value)
        if len(self._values) > self._max_samples:
            self._values = self._values[-self._max_samples:]
    
    @property
    def count(self) -> int:
        return len(self._values)
    
    @property
    def sum(self) -> float:
        return sum(self._values) if self._values else 0.0
    
    @property
    def avg(self) -> float:
        return self.sum / self.count if self.count > 0 else 0.0
    
    @property
    def percentiles(self) -> Dict[int, float]:
        if not self._values:
            return {}
        
        sorted_values = sorted(self._values)
        n = len(sorted_values)
        
        return {
            50: sorted_values[int(n * 0.50)],
            90: sorted_values[int(n * 0.90)],
            95: sorted_values[int(n * 0.95)],
            99: sorted_values[min(int(n * 0.99), n - 1)],
        }


class RateCounter:
    """Compteur avec calcul de taux (par seconde)"""
    
    def __init__(self, name: str, window_seconds: int = 60):
        self.name = name
        self.window_seconds = window_seconds
        self._events: List[datetime] = []
        self._lock = asyncio.Lock()
    
    async def record(self) -> None:
        now = datetime.now()
        async with self._lock:
            self._events.append(now)
            # Nettoyer les anciens événements
            cutoff = now - timedelta(seconds=self.window_seconds)
            self._events = [e for e in self._events if e > cutoff]
    
    def record_sync(self) -> None:
        now = datetime.now()
        self._events.append(now)
        cutoff = now - timedelta(seconds=self.window_seconds)
        self._events = [e for e in self._events if e > cutoff]
    
    @property
    def rate(self) -> float:
        """Événements par seconde"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)
        recent = [e for e in self._events if e > cutoff]
        return len(recent) / self.window_seconds if self.window_seconds > 0 else 0.0
    
    @property
    def count(self) -> int:
        return len(self._events)


class MetricsCollector:
    """
    Collecteur central de métriques (Singleton)
    """
    
    _instance: Optional['MetricsCollector'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Connexions
        self.connections_total = Counter('tm20_connections_total')
        self.connections_active = Gauge('tm20_connections_active')
        self.connections_errors = Counter('tm20_connection_errors_total')
        
        # Messages
        self.messages_received = Counter('tm20_messages_received_total')
        self.messages_sent = Counter('tm20_messages_sent_total')
        self.messages_rate = RateCounter('tm20_messages_rate', window_seconds=60)
        
        # Logs
        self.logs_received = Counter('tm20_attendance_logs_total')
        self.logs_rate = RateCounter('tm20_logs_rate', window_seconds=60)
        
        # Latence
        self.message_latency = Histogram('tm20_message_latency_seconds')
        self.db_write_latency = Histogram('tm20_db_write_latency_seconds')
        
        # Commandes
        self.commands_sent = Counter('tm20_commands_sent_total')
        self.commands_success = Counter('tm20_commands_success_total')
        self.commands_failed = Counter('tm20_commands_failed_total')
        
        # Par terminal
        self._per_device_messages: Dict[str, int] = defaultdict(int)
        self._per_device_logs: Dict[str, int] = defaultdict(int)
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'MetricsCollector':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def record_connection(self, sn: str) -> None:
        """Enregistre une nouvelle connexion"""
        self.connections_total.increment_sync()
    
    def record_disconnection(self, sn: str) -> None:
        """Enregistre une déconnexion"""
        pass  # Le gauge est mis à jour par update_active_connections
    
    def update_active_connections(self, count: int) -> None:
        """Met à jour le nombre de connexions actives"""
        self.connections_active.set_sync(count)
    
    def record_message(self, sn: str, direction: str = 'received') -> None:
        """Enregistre un message"""
        if direction == 'received':
            self.messages_received.increment_sync()
        else:
            self.messages_sent.increment_sync()
        self.messages_rate.record_sync()
        self._per_device_messages[sn] += 1
        self._sync_to_redis()
    
    def record_log(self, sn: str, count: int = 1) -> None:
        """Enregistre des logs de pointage"""
        self.logs_received.increment_sync(count)
        for _ in range(count):
            self.logs_rate.record_sync()
        self._per_device_logs[sn] += count
    
    def record_latency(self, metric: str, seconds: float) -> None:
        """Enregistre une latence"""
        if metric == 'message':
            self.message_latency.observe_sync(seconds)
        elif metric == 'db_write':
            self.db_write_latency.observe_sync(seconds)
        self._sync_to_redis()
    
    def record_command(self, success: bool) -> None:
        """Enregistre le résultat d'une commande"""
        self.commands_sent.increment_sync()
        if success:
            self.commands_success.increment_sync()
        else:
            self.commands_failed.increment_sync()
    
    def get_device_stats(self, sn: str) -> dict:
        """Stats pour un terminal spécifique"""
        return {
            'messages': self._per_device_messages.get(sn, 0),
            'logs': self._per_device_logs.get(sn, 0),
        }
    
    def get_all_stats(self) -> dict:
        """Toutes les métriques"""
        return {
            'connections': {
                'total': self.connections_total.value,
                'active': self.connections_active.value,
                'errors': self.connections_errors.value,
            },
            'messages': {
                'received': self.messages_received.value,
                'sent': self.messages_sent.value,
                'rate_per_second': round(self.messages_rate.rate, 2),
            },
            'logs': {
                'total': self.logs_received.value,
                'rate_per_second': round(self.logs_rate.rate, 2),
            },
            'latency': {
                'message_avg_ms': round(self.message_latency.avg * 1000, 2),
                'message_p95_ms': round(
                    self.message_latency.percentiles.get(95, 0.0) * 1000, 2
                ) if self.message_latency.percentiles else 0.0,
                'db_write_avg_ms': round(self.db_write_latency.avg * 1000, 2),
            },
            'commands': {
                'sent': self.commands_sent.value,
                'success': self.commands_success.value,
                'failed': self.commands_failed.value,
                'success_rate': round(
                    self.commands_success.value / max(self.commands_sent.value, 1) * 100, 1
                ),
            },
        }
    
    def reset(self) -> None:
        """Reset toutes les métriques"""
        self._per_device_messages.clear()
        self._per_device_logs.clear()
    
    def _sync_to_redis(self) -> None:
        """Synchronise les métriques vers Redis (throttled)"""
        try:
            stats = self.get_all_stats()
            cache.set('tm20:metrics', stats, timeout=60)
        except Exception as e:
            logger.error(f"Error syncing metrics to Redis: {e}")
    
    @staticmethod
    def get_stats_from_redis() -> dict:
        """Récupère les métriques depuis Redis (pour django-http)"""
        try:
            stats = cache.get('tm20:metrics')
            if stats:
                return stats
        except Exception as e:
            logger.error(f"Error reading metrics from Redis: {e}")
        
        # Retourner des métriques vides par défaut
        return {
            'connections': {'total': 0, 'active': 0, 'errors': 0},
            'messages': {'received': 0, 'sent': 0, 'rate_per_second': 0.0},
            'logs': {'total': 0, 'rate_per_second': 0.0},
            'latency': {'message_avg_ms': 0.0, 'message_p95_ms': 0.0, 'db_write_avg_ms': 0.0},
            'commands': {'sent': 0, 'success': 0, 'failed': 0, 'success_rate': 0.0},
        }


# Instance globale
metrics = MetricsCollector.get_instance()
