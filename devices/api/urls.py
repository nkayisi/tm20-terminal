"""
API URLs - Routes REST pour la gestion du système

Structure des endpoints:
- /api/configs/                     - Configurations services tiers
- /api/terminals/<id>/mappings/     - Mappings terminal <-> config
- /api/terminals/<id>/users/        - Utilisateurs d'un terminal
- /api/terminals/<id>/users/sync/   - Synchronisation utilisateurs
- /api/terminals/<id>/schedules/    - Horaires d'un terminal
- /api/attendance/sync/             - Synchronisation pointages
- /api/attendance/status/           - Statut synchronisation
- /api/attendance/dead-letter/      - Pointages en échec
"""

from django.urls import path

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

app_name = 'api'

urlpatterns = [
    # Configurations services tiers
    path('configs/', ThirdPartyConfigListView.as_view(), name='config_list'),
    path('configs/<int:config_id>/', ThirdPartyConfigDetailView.as_view(), name='config_detail'),
    
    # Mappings terminal <-> configuration
    path('terminals/<int:terminal_id>/mappings/', TerminalMappingView.as_view(), name='terminal_mappings'),
    
    # Utilisateurs d'un terminal
    path('terminals/<int:terminal_id>/users/', TerminalUsersView.as_view(), name='terminal_users'),
    path('terminals/<int:terminal_id>/users/sync/', UserSyncView.as_view(), name='user_sync'),
    path('terminals/<int:terminal_id>/users/sync/status/', UserSyncStatusView.as_view(), name='user_sync_status'),
    
    # Horaires d'un terminal
    path('terminals/<int:terminal_id>/schedules/', TerminalScheduleListView.as_view(), name='schedule_list'),
    path('terminals/<int:terminal_id>/schedules/<int:schedule_id>/', TerminalScheduleDetailView.as_view(), name='schedule_detail'),
    
    # Synchronisation pointages
    path('attendance/sync/', AttendanceSyncView.as_view(), name='attendance_sync'),
    path('attendance/status/', AttendanceSyncStatusView.as_view(), name='attendance_status'),
    path('attendance/dead-letter/', DeadLetterView.as_view(), name='dead_letter'),
]
