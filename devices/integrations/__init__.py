"""
Integrations - Adapters pour les services tiers

Architecture modulaire permettant d'ajouter facilement de nouvelles sources externes.
Chaque adapter implémente l'interface ThirdPartyAdapter.
"""

from .base import (
    ThirdPartyAdapter,
    AdapterResponse,
    AdapterError,
    UserData,
    AttendanceData,
)
from .http_adapter import HTTPAdapter
from .adapter_factory import AdapterFactory

__all__ = [
    'ThirdPartyAdapter',
    'AdapterResponse', 
    'AdapterError',
    'UserData',
    'AttendanceData',
    'HTTPAdapter',
    'AdapterFactory',
]
