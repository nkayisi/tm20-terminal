"""
Handler pour les réponses du terminal aux commandes serveur
"""

import logging
from typing import Any, Dict, Optional

from ..models import Terminal
from ..protocol import TM20Parser
from ..services.commands import CommandService
from ..core.events import EventBus, EventType
from .base import BaseHandler, HandlerResult

logger = logging.getLogger('devices.handlers')


class ResponseHandler(BaseHandler):
    """
    Gère les réponses du terminal (ret)
    """
    
    def __init__(self):
        self._service = CommandService()
        self._event_bus = EventBus.get_instance()
    
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional[Terminal] = None,
        sn: Optional[str] = None
    ) -> HandlerResult:
        """Traite une réponse du terminal"""
        
        ret = message.get('ret', '')
        result, reason, data = TM20Parser.parse_response_result(message)
        
        logger.info(f"[{sn or 'unknown'}] Response {ret}: {result}")
        
        # Traiter les réponses spécifiques
        if ret == 'setuserinfo' and terminal:
            await self._handle_setuserinfo_response(message, terminal, result)
        elif ret == 'setusername' and terminal:
            await self._handle_setusername_response(message, terminal, result)
        
        # Émettre l'événement
        await self._event_bus.emit(
            EventType.COMMAND_RESPONSE,
            {
                'sn': sn,
                'ret': ret,
                'result': result,
                'reason': reason,
                'data': data,
            },
            source='ResponseHandler'
        )
        
        # Les réponses n'ont pas besoin de réponse
        return HandlerResult.ok(
            response=None,
            ret=ret,
            result=result,
            data=data
        )
    
    async def _handle_setuserinfo_response(
        self,
        message: Dict[str, Any],
        terminal: Terminal,
        result: str
    ) -> None:
        """
        Traite la réponse setuserinfo du terminal.
        Marque l'utilisateur comme synchronisé si succès.
        """
        from asgiref.sync import sync_to_async
        from django.utils import timezone
        from ..models import BiometricUser
        
        enrollid = message.get('enrollid')
        if not enrollid:
            logger.warning(f"Réponse setuserinfo sans enrollid: {message}")
            return
        
        if result is True or result == 'ok':
            # Marquer l'utilisateur comme synchronisé
            @sync_to_async
            def mark_user_synced():
                try:
                    user = BiometricUser.objects.get(
                        terminal=terminal,
                        enrollid=enrollid
                    )
                    user.sync_status = 'synced_to_terminal'
                    user.last_synced_at = timezone.now()
                    user.save(update_fields=['sync_status', 'last_synced_at', 'updated_at'])
                    logger.info(
                        f"Utilisateur {enrollid} marqué comme synchronisé "
                        f"sur terminal {terminal.sn}"
                    )
                except BiometricUser.DoesNotExist:
                    logger.warning(
                        f"Utilisateur {enrollid} introuvable pour terminal {terminal.sn}"
                    )
            
            await mark_user_synced()
        else:
            # Marquer comme erreur
            @sync_to_async
            def mark_user_error():
                try:
                    user = BiometricUser.objects.get(
                        terminal=terminal,
                        enrollid=enrollid
                    )
                    user.sync_status = 'error'
                    user.save(update_fields=['sync_status', 'updated_at'])
                    logger.error(
                        f"Erreur synchronisation utilisateur {enrollid} "
                        f"sur terminal {terminal.sn}: {result}"
                    )
                except BiometricUser.DoesNotExist:
                    logger.warning(
                        f"Utilisateur {enrollid} introuvable pour terminal {terminal.sn}"
                    )
            
            await mark_user_error()
    
    async def _handle_setusername_response(
        self,
        message: Dict[str, Any],
        terminal: Terminal,
        result: str
    ) -> None:
        """
        Traite la réponse setusername du terminal.
        Marque les utilisateurs comme synchronisés si succès.
        
        Note: Les métadonnées (_user_ids) sont stockées dans le cache Redis
        lors de l'envoi de la commande et récupérées ici.
        """
        from asgiref.sync import sync_to_async
        from django.utils import timezone
        from django.core.cache import cache
        from ..models import BiometricUser
        
        # Récupérer les métadonnées depuis le cache Redis
        cache_key = f'setusername_pending:{terminal.sn}'
        cached_data = cache.get(cache_key)
        
        user_ids = None
        enrollids = None
        
        if cached_data:
            user_ids = cached_data.get('user_ids', [])
            enrollids = cached_data.get('enrollids', [])
            logger.info(
                f"Métadonnées récupérées du cache pour {terminal.sn}: "
                f"{len(user_ids)} utilisateurs (IDs: {user_ids})"
            )
            # Supprimer du cache après utilisation
            cache.delete(cache_key)
        else:
            # Fallback: essayer de récupérer depuis record (peu probable)
            record = message.get('record', [])
            logger.warning(
                f"Réponse setusername sans cache, utilisation de record "
                f"({len(record)} utilisateurs)"
            )
            enrollids = [u.get('enrollid') for u in record if u.get('enrollid')]
        
        if result is True or result == 'ok':
            # Marquer tous les utilisateurs comme synchronisés
            @sync_to_async
            def mark_users_synced():
                if user_ids:
                    # Marquer par IDs (méthode préférée)
                    count = BiometricUser.objects.filter(
                        id__in=user_ids,
                        terminal=terminal
                    ).update(
                        sync_status='synced_to_terminal',
                        last_synced_at=timezone.now()
                    )
                    logger.info(
                        f"{count} utilisateurs marqués comme synchronisés "
                        f"sur terminal {terminal.sn} (IDs: {user_ids})"
                    )
                elif enrollids:
                    # Fallback: marquer par enrollid
                    count = BiometricUser.objects.filter(
                        terminal=terminal,
                        enrollid__in=enrollids
                    ).update(
                        sync_status='synced_to_terminal',
                        last_synced_at=timezone.now()
                    )
                    logger.info(
                        f"{count} utilisateurs marqués comme synchronisés "
                        f"sur terminal {terminal.sn} (enrollids: {enrollids})"
                    )
            
            await mark_users_synced()
        else:
            # Marquer comme erreur
            @sync_to_async
            def mark_users_error():
                if user_ids:
                    count = BiometricUser.objects.filter(
                        id__in=user_ids,
                        terminal=terminal
                    ).update(sync_status='error')
                    logger.error(
                        f"{count} utilisateurs marqués en erreur "
                        f"sur terminal {terminal.sn}: {result}"
                    )
                elif enrollids:
                    count = BiometricUser.objects.filter(
                        terminal=terminal,
                        enrollid__in=enrollids
                    ).update(sync_status='error')
                    logger.error(
                        f"{count} utilisateurs marqués en erreur "
                        f"sur terminal {terminal.sn}: {result}"
                    )
            
            await mark_users_error()
