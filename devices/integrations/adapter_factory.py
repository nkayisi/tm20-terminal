"""
Adapter Factory - Factory pour créer les adapters appropriés

Permet d'ajouter facilement de nouveaux types d'adapters sans modifier
le code existant.
"""

import logging
from typing import Dict, Type, Optional

from .base import ThirdPartyAdapter, AdapterError
from .http_adapter import HTTPAdapter

logger = logging.getLogger(__name__)


class AdapterFactory:
    """
    Factory pour créer des instances d'adapters.
    
    Utilisation:
        adapter = AdapterFactory.create(config)
        users = await adapter.fetch_users()
    
    Pour ajouter un nouveau type d'adapter:
        AdapterFactory.register('custom', CustomAdapter)
    """
    
    _adapters: Dict[str, Type[ThirdPartyAdapter]] = {
        'http': HTTPAdapter,
        'rest': HTTPAdapter,
        'api': HTTPAdapter,
    }
    
    @classmethod
    def register(cls, adapter_type: str, adapter_class: Type[ThirdPartyAdapter]):
        """
        Enregistre un nouveau type d'adapter.
        
        Args:
            adapter_type: Identifiant du type d'adapter
            adapter_class: Classe de l'adapter (doit hériter de ThirdPartyAdapter)
        """
        if not issubclass(adapter_class, ThirdPartyAdapter):
            raise ValueError(f"{adapter_class} doit hériter de ThirdPartyAdapter")
        
        cls._adapters[adapter_type.lower()] = adapter_class
        logger.info(f"Adapter '{adapter_type}' enregistré: {adapter_class.__name__}")
    
    @classmethod
    def create(cls, config: 'ThirdPartyConfig') -> ThirdPartyAdapter:
        """
        Crée une instance d'adapter basée sur la configuration.
        
        Args:
            config: Configuration du service tiers
            
        Returns:
            Instance de ThirdPartyAdapter appropriée
            
        Raises:
            AdapterError: Si le type d'adapter n'est pas supporté
        """
        adapter_type = getattr(config, 'adapter_type', 'http').lower()
        
        if adapter_type not in cls._adapters:
            logger.warning(f"Type d'adapter '{adapter_type}' non trouvé, utilisation de 'http'")
            adapter_type = 'http'
        
        adapter_class = cls._adapters[adapter_type]
        logger.debug(f"Création d'adapter {adapter_class.__name__} pour {config.name}")
        
        return adapter_class(config)
    
    @classmethod
    def get_available_types(cls) -> list:
        """Retourne la liste des types d'adapters disponibles"""
        return list(cls._adapters.keys())
    
    @classmethod
    def unregister(cls, adapter_type: str) -> bool:
        """
        Supprime un type d'adapter enregistré.
        
        Args:
            adapter_type: Identifiant du type d'adapter
            
        Returns:
            True si l'adapter a été supprimé, False sinon
        """
        adapter_type = adapter_type.lower()
        if adapter_type in cls._adapters:
            del cls._adapters[adapter_type]
            return True
        return False
