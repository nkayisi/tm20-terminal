"""
Handler pour les utilisateurs (senduser)
"""

import logging
from typing import Any, Dict, Optional

from ..models import Terminal
from ..protocol import TM20Parser, ResponseBuilder
from ..services.users import UserService
from .base import BaseHandler, HandlerResult

logger = logging.getLogger('devices.handlers')


class UserHandler(BaseHandler):
    """
    Gère les messages d'utilisateurs (senduser)
    """
    
    def __init__(self):
        self._service = UserService()
    
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional[Terminal] = None,
        sn: Optional[str] = None,
        **context: Any
    ) -> HandlerResult:
        """Traite un message senduser"""
        
        if not terminal:
            response = ResponseBuilder.senduser(success=False)
            return HandlerResult.fail("Terminal not registered", response)
        
        # Parser le message
        user_msg = TM20Parser.parse_senduser(message)
        
        # Traiter l'utilisateur
        success = await self._service.process_user(terminal, user_msg)
        
        # Construire la réponse
        response = ResponseBuilder.senduser(success=success)
        
        if success:
            return HandlerResult.ok(
                response=response,
                enrollid=user_msg.enrollid,
                backupnum=user_msg.backupnum
            )
        else:
            return HandlerResult.fail("Failed to process user", response)
