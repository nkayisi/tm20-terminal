"""
Service d'enregistrement des terminaux
"""

import logging
from typing import Optional, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from ..models import Terminal
from ..protocol import RegisterMessage
from ..core.events import EventBus, EventType
from ..core.metrics import MetricsCollector

logger = logging.getLogger('devices.services')


class RegistrationService:
    """
    Service de gestion de l'enregistrement des terminaux
    Responsabilités :
    - Validation du SN
    - Vérification whitelist
    - Création/mise à jour du terminal en DB
    - Émission des événements
    """
    
    def __init__(self):
        self._event_bus = EventBus.get_instance()
        self._metrics = MetricsCollector.get_instance()
    
    @sync_to_async
    def register(self, reg_msg: RegisterMessage) -> Tuple[Terminal, bool]:
        """
        Enregistre ou met à jour un terminal
        Retourne (terminal, created)
        """
        devinfo = reg_msg.devinfo
        
        defaults = {
            'cpusn': reg_msg.cpusn,
            'last_seen': timezone.now(),
            'is_active': True,
        }
        
        if devinfo:
            defaults.update({
                'model': devinfo.modelname,
                'firmware': devinfo.firmware,
                'mac_address': devinfo.mac,
                'user_capacity': devinfo.usersize,
                'fp_capacity': devinfo.fpsize,
                'card_capacity': devinfo.cardsize,
                'log_capacity': devinfo.logsize,
                'used_users': devinfo.useduser,
                'used_fp': devinfo.usedfp,
                'used_cards': devinfo.usedcard,
                'used_logs': devinfo.usedlog,
                'fp_algo': devinfo.fpalgo,
            })
        
        terminal, created = Terminal.objects.update_or_create(
            sn=reg_msg.sn,
            defaults=defaults
        )
        
        action = "created" if created else "updated"
        logger.info(f"Terminal {action}: {terminal.sn} ({terminal.model})")
        
        # Métriques
        self._metrics.record_connection(reg_msg.sn)
        
        return terminal, created
    
    @sync_to_async
    def is_whitelisted(self, sn: str) -> bool:
        """Vérifie si un terminal est autorisé à se connecter"""
        if not settings.TM20_SETTINGS.get('REQUIRE_WHITELIST', False):
            return True
        
        try:
            terminal = Terminal.objects.get(sn=sn)
            return terminal.is_whitelisted and terminal.is_active
        except Terminal.DoesNotExist:
            return False
    
    @sync_to_async
    def get_terminal(self, sn: str) -> Optional[Terminal]:
        """Récupère un terminal par SN"""
        try:
            return Terminal.objects.get(sn=sn)
        except Terminal.DoesNotExist:
            return None
    
    @sync_to_async
    def update_status(self, sn: str, is_active: bool = True) -> None:
        """Met à jour le statut d'un terminal"""
        Terminal.objects.filter(sn=sn).update(
            is_active=is_active,
            last_seen=timezone.now()
        )
    
    @sync_to_async
    def update_last_seen(self, sn: str) -> None:
        """Met à jour le timestamp de dernière activité"""
        Terminal.objects.filter(sn=sn).update(last_seen=timezone.now())
    
    @sync_to_async
    def get_terminal_info(self, sn: str) -> Optional[dict]:
        """Récupère les infos d'un terminal pour le dashboard"""
        try:
            t = Terminal.objects.get(sn=sn)
            return {
                'sn': t.sn,
                'model': t.model,
                'firmware': t.firmware,
                'mac_address': t.mac_address,
                'is_active': t.is_active,
                'is_whitelisted': t.is_whitelisted,
                'last_seen': t.last_seen.isoformat() if t.last_seen else None,
                'user_capacity': t.user_capacity,
                'used_users': t.used_users,
                'fp_capacity': t.fp_capacity,
                'used_fp': t.used_fp,
            }
        except Terminal.DoesNotExist:
            return None


# Instance par défaut
registration_service = RegistrationService()
