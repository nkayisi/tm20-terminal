"""
Base classes pour les adapters de services tiers

Définit l'interface commune que tous les adapters doivent implémenter.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AdapterError(Exception):
    """Exception de base pour les erreurs d'adapter"""
    
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code or 'ADAPTER_ERROR'
        self.details = details or {}
    
    def to_dict(self) -> dict:
        return {
            'error': self.message,
            'code': self.code,
            'details': self.details,
        }


class ConnectionError(AdapterError):
    """Erreur de connexion au service tiers"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 'CONNECTION_ERROR', details)


class AuthenticationError(AdapterError):
    """Erreur d'authentification"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 'AUTH_ERROR', details)


class ValidationError(AdapterError):
    """Erreur de validation des données"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 'VALIDATION_ERROR', details)


class RateLimitError(AdapterError):
    """Erreur de rate limiting"""
    def __init__(self, message: str, retry_after: int = None, details: dict = None):
        details = details or {}
        details['retry_after'] = retry_after
        super().__init__(message, 'RATE_LIMIT_ERROR', details)
        self.retry_after = retry_after


@dataclass
class AdapterResponse:
    """Réponse standardisée d'un adapter"""
    
    success: bool
    data: Any = None
    message: str = ''
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok(cls, data: Any = None, message: str = '', metadata: dict = None):
        """Crée une réponse de succès"""
        return cls(
            success=True,
            data=data,
            message=message,
            metadata=metadata or {}
        )
    
    @classmethod
    def error(cls, message: str, errors: List[str] = None, metadata: dict = None):
        """Crée une réponse d'erreur"""
        return cls(
            success=False,
            message=message,
            errors=errors or [message],
            metadata=metadata or {}
        )
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'data': self.data,
            'message': self.message,
            'errors': self.errors,
            'metadata': self.metadata,
        }


@dataclass
class UserData:
    """Données utilisateur standardisées provenant d'un service tiers"""
    
    external_id: str
    fullname: str
    is_enabled: bool = True
    admin_level: int = 0
    group: int = 0
    weekzone: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'external_id': self.external_id,
            'fullname': self.fullname,
            'is_enabled': self.is_enabled,
            'admin_level': self.admin_level,
            'group': self.group,
            'weekzone': self.weekzone,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'metadata': self.metadata,
        }


@dataclass
class AttendanceData:
    """Données de pointage à envoyer vers un service tiers"""
    
    log_id: int
    terminal_sn: str
    enrollid: int
    external_user_id: Optional[str]
    user_name: str
    timestamp: str
    mode: int
    inout: int
    event: int = 0
    temperature: Optional[float] = None
    access_granted: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'log_id': self.log_id,
            'terminal_sn': self.terminal_sn,
            'enrollid': self.enrollid,
            'external_user_id': self.external_user_id,
            'user_name': self.user_name,
            'timestamp': self.timestamp,
            'mode': self.mode,
            'inout': self.inout,
            'event': self.event,
            'temperature': self.temperature,
            'access_granted': self.access_granted,
            'metadata': self.metadata,
        }


class ThirdPartyAdapter(ABC):
    """
    Interface de base pour tous les adapters de services tiers.
    
    Chaque adapter doit implémenter les méthodes abstraites pour:
    - Récupérer les utilisateurs depuis le service tiers
    - Envoyer les pointages vers le service tiers
    - Tester la connexion
    """
    
    def __init__(self, config: 'ThirdPartyConfig'):
        """
        Initialise l'adapter avec une configuration.
        
        Args:
            config: Instance de ThirdPartyConfig contenant les paramètres de connexion
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    async def test_connection(self) -> AdapterResponse:
        """
        Teste la connexion au service tiers.
        
        Returns:
            AdapterResponse indiquant si la connexion est réussie
        """
        pass
    
    @abstractmethod
    async def fetch_users(self, **kwargs) -> AdapterResponse:
        """
        Récupère la liste des utilisateurs depuis le service tiers.
        
        Returns:
            AdapterResponse contenant une liste de UserData
        """
        pass
    
    @abstractmethod
    async def send_attendance(self, attendance_list: List[AttendanceData]) -> AdapterResponse:
        """
        Envoie une liste de pointages vers le service tiers.
        
        Args:
            attendance_list: Liste de AttendanceData à envoyer
            
        Returns:
            AdapterResponse indiquant le résultat de l'envoi
        """
        pass
    
    def get_headers(self) -> Dict[str, str]:
        """Construit les headers HTTP avec authentification"""
        headers = {'Content-Type': 'application/json'}
        
        if self.config.auth_type == 'bearer':
            headers[self.config.auth_header_name] = f'Bearer {self.config.auth_token}'
        elif self.config.auth_type == 'api_key':
            headers[self.config.auth_header_name] = self.config.auth_token
        elif self.config.auth_type == 'basic':
            import base64
            encoded = base64.b64encode(self.config.auth_token.encode()).decode()
            headers[self.config.auth_header_name] = f'Basic {encoded}'
        
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        
        return headers
    
    def build_url(self, endpoint: str) -> str:
        """Construit l'URL complète à partir de l'endpoint"""
        base = self.config.base_url.rstrip('/')
        endpoint = endpoint.lstrip('/')
        return f"{base}/{endpoint}"
