"""
Handler pour les logs de pointage (sendlog)
"""

import logging
from typing import Any, Dict, Optional

from ..models import Terminal
from ..protocol import TM20Parser, ResponseBuilder
from ..services.attendance import AttendanceService
from ..services.registration import RegistrationService
from .base import BaseHandler, HandlerResult

logger = logging.getLogger('devices.handlers')


class AttendanceHandler(BaseHandler):
    """
    Gère les messages de logs de pointage (sendlog)
    """
    
    def __init__(self):
        self._service = AttendanceService()
        self._registration = RegistrationService()
    
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional[Terminal] = None,
        sn: Optional[str] = None
    ) -> HandlerResult:
        """Traite un message sendlog"""
        
        if not terminal:
            response = ResponseBuilder.sendlog(success=False)
            return HandlerResult.fail("Terminal not registered", response)
        
        # Vérifier le SN
        msg_sn = message.get('sn', '')
        if msg_sn and msg_sn != terminal.sn:
            logger.warning(f"SN mismatch: expected {terminal.sn}, got {msg_sn}")
        
        # Parser les logs
        log_msg = TM20Parser.parse_sendlog(message)
        
        # Traiter les logs
        processed, access_granted = await self._service.process_logs(
            terminal, log_msg
        )
        
        # Mettre à jour last_seen
        await self._registration.update_last_seen(terminal.sn)
        
        # Construire la réponse
        response = ResponseBuilder.sendlog(
            success=True,
            count=processed,
            logindex=log_msg.logindex,
            access=1 if access_granted else 0
        )
        
        return HandlerResult.ok(
            response=response,
            processed=processed,
            access_granted=access_granted
        )
