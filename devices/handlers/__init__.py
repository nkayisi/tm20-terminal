"""
Message Handlers - Traitement des messages du protocole TM20
Séparation claire des responsabilités par type de message
"""

from .base import BaseHandler, HandlerResult
from .registration import RegistrationHandler
from .attendance import AttendanceHandler
from .user import UserHandler
from .qrcode import QRCodeHandler
from .response import ResponseHandler

__all__ = [
    'BaseHandler',
    'HandlerResult',
    'RegistrationHandler',
    'AttendanceHandler',
    'UserHandler',
    'QRCodeHandler',
    'ResponseHandler',
]
