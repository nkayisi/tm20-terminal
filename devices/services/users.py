"""
Service de gestion des utilisateurs biométriques
"""

import logging
from typing import List, Optional

from asgiref.sync import sync_to_async
from django.db import transaction

from ..models import BiometricCredential, BiometricUser, Terminal
from ..protocol import SendUserMessage
from ..core.events import EventBus, EventType

logger = logging.getLogger('devices.services')


class UserService:
    """
    Service de gestion des utilisateurs biométriques
    """
    
    def __init__(self):
        self._event_bus = EventBus.get_instance()
    
    @sync_to_async
    def process_user(self, terminal: Terminal, user_msg: SendUserMessage) -> bool:
        """Traite un utilisateur envoyé par le terminal"""
        try:
            with transaction.atomic():
                user, created = BiometricUser.objects.update_or_create(
                    terminal=terminal,
                    enrollid=user_msg.enrollid,
                    defaults={
                        'name': user_msg.name,
                        'admin': user_msg.admin,
                    }
                )
                
                if user_msg.record is not None:
                    BiometricCredential.objects.update_or_create(
                        user=user,
                        backupnum=user_msg.backupnum,
                        defaults={'record': str(user_msg.record)}
                    )
                
                action = "created" if created else "updated"
                logger.info(
                    f"[{terminal.sn}] User {user_msg.enrollid} {action} "
                    f"(backupnum={user_msg.backupnum})"
                )
                return True
                
        except Exception as e:
            logger.error(f"Error processing user: {e}")
            return False
    
    @sync_to_async
    def get_user(
        self,
        terminal: Terminal,
        enrollid: int
    ) -> Optional[BiometricUser]:
        """Récupère un utilisateur"""
        try:
            return BiometricUser.objects.get(
                terminal=terminal,
                enrollid=enrollid
            )
        except BiometricUser.DoesNotExist:
            return None
    
    @sync_to_async
    def set_enabled(
        self,
        terminal: Terminal,
        enrollid: int,
        enabled: bool
    ) -> bool:
        """Active/désactive un utilisateur"""
        updated = BiometricUser.objects.filter(
            terminal=terminal,
            enrollid=enrollid
        ).update(is_enabled=enabled)
        return updated > 0
    
    @sync_to_async
    def delete_user(self, terminal: Terminal, enrollid: int) -> bool:
        """Supprime un utilisateur"""
        deleted, _ = BiometricUser.objects.filter(
            terminal=terminal,
            enrollid=enrollid
        ).delete()
        return deleted > 0
    
    @sync_to_async
    def get_all_users(self, terminal: Terminal) -> List[dict]:
        """Récupère tous les utilisateurs d'un terminal"""
        users = BiometricUser.objects.filter(
            terminal=terminal
        ).prefetch_related('credentials')
        
        return [
            {
                'enrollid': u.enrollid,
                'name': u.name,
                'admin': u.admin,
                'is_enabled': u.is_enabled,
                'credentials_count': u.credentials.count(),
            }
            for u in users
        ]
    
    @sync_to_async
    def get_users_count(self, terminal: Terminal = None) -> int:
        """Compte les utilisateurs"""
        queryset = BiometricUser.objects.all()
        if terminal:
            queryset = queryset.filter(terminal=terminal)
        return queryset.count()


# Instance par défaut
user_service = UserService()
