"""
Base handler et types communs
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Terminal


@dataclass
class HandlerResult:
    """Résultat d'un handler"""
    success: bool
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok(cls, response: dict = None, **data) -> 'HandlerResult':
        return cls(success=True, response=response, data=data)
    
    @classmethod
    def fail(cls, error: str, response: dict = None) -> 'HandlerResult':
        return cls(success=False, error=error, response=response)


class BaseHandler(ABC):
    """
    Classe de base pour tous les handlers de messages
    
    Responsabilités :
    - Traiter un type de message spécifique
    - Retourner une réponse formatée
    - Ne PAS gérer le transport (WebSocket)
    """
    
    @abstractmethod
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional['Terminal'] = None,
        sn: Optional[str] = None
    ) -> HandlerResult:
        """
        Traite le message et retourne le résultat
        
        Args:
            message: Message JSON parsé
            terminal: Terminal enregistré (si disponible)
            sn: Serial number (si disponible avant registration)
        
        Returns:
            HandlerResult avec la réponse à envoyer
        """
        pass
