"""
Service de gestion des commandes vers les terminaux
"""

import logging
from typing import List, Optional

from asgiref.sync import sync_to_async
from django.utils import timezone

from ..models import CommandQueue, Terminal
from ..core.events import EventBus, EventType
from ..core.metrics import MetricsCollector

logger = logging.getLogger('devices.services')


class CommandService:
    """
    Service de gestion de la file d'attente des commandes
    """
    
    def __init__(self):
        self._event_bus = EventBus.get_instance()
        self._metrics = MetricsCollector.get_instance()
    
    @sync_to_async
    def queue(
        self,
        terminal: Terminal,
        command: str,
        payload: dict
    ) -> CommandQueue:
        """Ajoute une commande à la file d'attente"""
        cmd = CommandQueue.objects.create(
            terminal=terminal,
            command=command,
            payload=payload,
            status='pending'
        )
        logger.info(f"Command queued: {command} -> {terminal.sn}")
        return cmd
    
    @sync_to_async
    def get_pending(self, terminal: Terminal, limit: int = 10) -> List[CommandQueue]:
        """Récupère les commandes en attente"""
        return list(
            CommandQueue.objects.filter(
                terminal=terminal,
                status='pending'
            ).order_by('created_at')[:limit]
        )
    
    @sync_to_async
    def mark_sent(self, command_id: int) -> None:
        """Marque une commande comme envoyée"""
        CommandQueue.objects.filter(id=command_id).update(
            status='sent',
            sent_at=timezone.now()
        )
    
    @sync_to_async
    def mark_completed(
        self,
        command_id: int,
        success: bool,
        response: dict = None,
        error: str = ""
    ) -> None:
        """Marque une commande comme terminée"""
        status = 'success' if success else 'failed'
        CommandQueue.objects.filter(id=command_id).update(
            status=status,
            response=response,
            error_message=error,
            completed_at=timezone.now()
        )
        
        # Métriques
        self._metrics.record_command(success)
    
    @sync_to_async
    def get_history(
        self,
        terminal: Terminal = None,
        limit: int = 50
    ) -> List[dict]:
        """Récupère l'historique des commandes"""
        queryset = CommandQueue.objects.all()
        
        if terminal:
            queryset = queryset.filter(terminal=terminal)
        
        queryset = queryset.select_related('terminal')[:limit]
        
        return [
            {
                'id': cmd.id,
                'sn': cmd.terminal.sn,
                'command': cmd.command,
                'status': cmd.status,
                'created_at': cmd.created_at.isoformat(),
                'sent_at': cmd.sent_at.isoformat() if cmd.sent_at else None,
                'completed_at': cmd.completed_at.isoformat() if cmd.completed_at else None,
            }
            for cmd in queryset
        ]
    
    @sync_to_async
    def cleanup_old(self, days: int = 30) -> int:
        """Nettoie les anciennes commandes"""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=days)
        
        deleted, _ = CommandQueue.objects.filter(
            created_at__lt=cutoff,
            status__in=['success', 'failed', 'timeout']
        ).delete()
        
        if deleted:
            logger.info(f"Cleaned up {deleted} old commands")
        
        return deleted


# Instance par défaut
command_service = CommandService()
