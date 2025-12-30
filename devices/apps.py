"""
Configuration de l'application devices avec initialisation des singletons
"""

from django.apps import AppConfig


class DevicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'devices'
    verbose_name = 'Terminaux TM20'
    
    def ready(self):
        """Initialisation au démarrage de Django"""
        import asyncio
        
        # Initialiser les singletons
        from .core.device_manager import DeviceManager
        from .core.events import EventBus
        from .core.metrics import MetricsCollector
        
        # Les singletons sont initialisés au premier accès
        DeviceManager.get_instance()
        EventBus.get_instance()
        MetricsCollector.get_instance()
