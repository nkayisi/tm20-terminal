"""
Handler pour les QR codes (sendqrcode)
"""

import logging
from typing import Any, Dict, Optional

from ..models import Terminal
from ..protocol import ResponseBuilder
from ..services.access_control import AccessControlService
from .base import BaseHandler, HandlerResult

logger = logging.getLogger('devices.handlers')


class QRCodeHandler(BaseHandler):
    """
    Gère les messages de QR code (sendqrcode)
    """
    
    def __init__(self):
        self._service = AccessControlService()
    
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional[Terminal] = None,
        sn: Optional[str] = None
    ) -> HandlerResult:
        """Traite un message sendqrcode"""
        
        if not terminal:
            response = ResponseBuilder.sendqrcode(success=False)
            return HandlerResult.fail("Terminal not registered", response)
        
        qrcode = message.get('record', '')
        
        # Vérifier l'accès
        access, enrollid, username, msg = await self._service.check_qrcode_access(
            terminal, qrcode
        )
        
        # Construire la réponse
        response = ResponseBuilder.sendqrcode(
            success=True,
            access=1 if access else 0,
            enrollid=enrollid,
            username=username,
            message=msg
        )
        
        return HandlerResult.ok(
            response=response,
            access=access,
            enrollid=enrollid
        )
