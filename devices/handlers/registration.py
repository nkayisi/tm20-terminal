"""
Handler pour l'enregistrement des terminaux (reg)
"""

import logging
from typing import Any, Dict, Optional

from ..models import Terminal
from ..protocol import TM20Parser, ResponseBuilder
from ..services.registration import RegistrationService
from ..core.device_manager import DeviceManager
from ..core.events import EventBus, EventType
from .base import BaseHandler, HandlerResult

logger = logging.getLogger('devices.handlers')


class RegistrationHandler(BaseHandler):
    """
    Gère les messages d'enregistrement (reg)
    """
    
    def __init__(self):
        self._service = RegistrationService()
        self._event_bus = EventBus.get_instance()
    
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional[Terminal] = None,
        sn: Optional[str] = None,
        **context: Any
    ) -> HandlerResult:
        """Traite un message reg"""
        
        sn = message.get('sn', '')
        
        if not sn:
            response = ResponseBuilder.reg(
                success=False,
                reason="Missing SN"
            )
            return HandlerResult.fail("Missing SN", response)
        
        # Vérifier la whitelist
        if not await self._service.is_whitelisted(sn):
            logger.warning(f"Terminal not whitelisted: {sn}")
            response = ResponseBuilder.reg(
                success=False,
                reason="Terminal not authorized"
            )
            return HandlerResult.fail("Not whitelisted", response)
        
        # Parser et enregistrer
        reg_msg = TM20Parser.parse_register(message)
        terminal, created = await self._service.register(
            reg_msg, client_ip=context.get('client_ip')
        )
        
        # Émettre l'événement
        await self._event_bus.emit(
            EventType.DEVICE_REGISTERED,
            {
                'sn': sn,
                'model': terminal.model,
                'firmware': terminal.firmware,
                'created': created,
            },
            source='RegistrationHandler'
        )
        
        # Construire la réponse (cloudtime généré par le builder en heure terminal)
        #
        # nosenduser=True : le terminal ne remonte PAS automatiquement les
        # utilisateurs enroles a son clavier (doc section T1). Choix assume --
        # le serveur reste maitre du referentiel utilisateurs et les pousse via
        # setusername/setuserinfo. Le handler `senduser` reste en place et
        # redeviendra actif le jour ou ce drapeau passe a False.
        response = ResponseBuilder.reg(
            success=True,
            nosenduser=True
        )
        
        logger.info(f"Terminal registered: {sn} (new: {created})")
        
        return HandlerResult.ok(
            response=response,
            terminal=terminal,
            created=created,
            sn=sn
        )
