"""
URLs pour les API REST de gestion
"""

from django.urls import path
from . import api_views

urlpatterns = [
    # Configurations services tiers
    path('third-party-configs/', api_views.third_party_configs_api, name='third_party_configs'),
    path('third-party-configs/<int:config_id>/', api_views.third_party_config_detail_api, name='third_party_config_detail'),
    
    # Synchronisation utilisateurs
    path('sync/users/from-third-party/', api_views.sync_users_from_third_party_api, name='sync_users_from_third_party'),
    path('sync/users/to-terminal/', api_views.load_users_to_terminal_api, name='load_users_to_terminal'),
    
    # Horaires
    path('terminals/<int:terminal_id>/schedules/', api_views.terminal_schedules_api, name='terminal_schedules'),
    path('terminals/<int:terminal_id>/schedules/<int:schedule_id>/', api_views.terminal_schedule_detail_api, name='terminal_schedule_detail'),
    path('terminals/<int:terminal_id>/schedules/sync/', api_views.sync_schedule_to_terminal_api, name='sync_schedule_to_terminal'),
    
    # Synchronisation pointages
    path('attendance/sync-status/', api_views.attendance_sync_status_api, name='attendance_sync_status'),
    path('attendance/manual-sync/', api_views.manual_sync_attendance_api, name='manual_sync_attendance'),
    
    # Mappings terminal-service tiers
    path('terminals/<int:terminal_id>/mappings/', api_views.terminal_mappings_api, name='terminal_mappings'),
]
