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
    
    @staticmethod
    def is_connected(sn: str) -> bool:
        """Le terminal a-t-il une connexion WebSocket active ?

        La source de verite est Redis : le pool en memoire du DeviceManager
        n'existe que dans le process ASGI qui porte les WebSockets, jamais
        dans un process HTTP ou un worker Celery.
        """
        from ..core.device_manager import DeviceManager
        return sn in DeviceManager.get_connected_sns_from_redis()

    @staticmethod
    def dispatch(sn: str, payload: dict) -> bool:
        """Envoie une commande au terminal via la couche Channels.

        C'est le seul chemin valable depuis un contexte synchrone (vue HTTP,
        tache Celery) : le consumer a rejoint le groupe `terminal_<sn>` a son
        enregistrement et expose le handler `send_command`. Passer par
        `DeviceManager.send_to_device` depuis ces contextes ne fonctionne pas
        (singleton en memoire d'un autre process, et boucle asyncio distincte).

        Retourne True si la commande a ete remise a un terminal connecte.
        """
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        if not CommandService.is_connected(sn):
            logger.info(f"[{sn}] Terminal hors ligne, commande mise en file")
            return False

        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.error("Channel layer indisponible, commande mise en file")
            return False

        try:
            async_to_sync(channel_layer.group_send)(
                f'terminal_{sn}',
                {'type': 'send_command', 'command': payload},
            )
            logger.info(f"[{sn}] Commande {payload.get('cmd')} transmise")
            return True
        except Exception as e:
            logger.error(f"[{sn}] Echec transmission de la commande: {e}")
            return False

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
