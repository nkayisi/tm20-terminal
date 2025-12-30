"""
Protocol module - Parsing, validation et construction des messages TM20
"""

from .parser import TM20Parser
from .validators import MessageValidator, ValidationError
from .builders import ResponseBuilder, CommandBuilder
from .types import (
    CommandType,
    DeviceInfo,
    RegisterMessage,
    LogRecord,
    SendLogMessage,
    SendUserMessage,
    UserRecord,
)

__all__ = [
    'TM20Parser',
    'MessageValidator',
    'ValidationError',
    'ResponseBuilder',
    'CommandBuilder',
    'CommandType',
    'DeviceInfo',
    'RegisterMessage',
    'LogRecord',
    'SendLogMessage',
    'SendUserMessage',
    'UserRecord',
]
