"""
API Module - Endpoints REST pour la gestion du système
"""

from .views import (
    ThirdPartyConfigListView,
    ThirdPartyConfigDetailView,
    TerminalMappingView,
    UserSyncView,
    UserSyncStatusView,
    AttendanceSyncView,
    AttendanceSyncStatusView,
    DeadLetterView,
    TerminalScheduleListView,
    TerminalScheduleDetailView,
    TerminalUsersView,
)

__all__ = [
    'ThirdPartyConfigListView',
    'ThirdPartyConfigDetailView',
    'TerminalMappingView',
    'UserSyncView',
    'UserSyncStatusView',
    'AttendanceSyncView',
    'AttendanceSyncStatusView',
    'DeadLetterView',
    'TerminalScheduleListView',
    'TerminalScheduleDetailView',
    'TerminalUsersView',
]
