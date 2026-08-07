"""
Protocol module - Parsing, validation et construction des messages TM20
"""

from .parser import TM20Parser
from .validators import MessageValidator, ValidationError
from .builders import ResponseBuilder, CommandBuilder
from .time_utils import terminal_now_str, make_terminal_aware, terminal_timezone
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
    'terminal_now_str',
    'make_terminal_aware',
    'terminal_timezone',
    'CommandType',
    'DeviceInfo',
    'RegisterMessage',
    'LogRecord',
    'SendLogMessage',
    'SendUserMessage',
    'UserRecord',
]
