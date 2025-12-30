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
