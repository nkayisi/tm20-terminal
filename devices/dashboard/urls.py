"""
URLs du dashboard
"""

from django.urls import path

from . import views
from . import management_views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),
    path('api/', views.DashboardAPIView.as_view(), name='api'),
    path('api/terminals/', views.TerminalsAPIView.as_view(), name='terminals'),
    path('api/logs/', views.LogsAPIView.as_view(), name='logs'),
    path('api/events/', views.EventsAPIView.as_view(), name='events'),
    path('api/command/<str:sn>/', views.CommandAPIView.as_view(), name='command'),
    
    # Vues de gestion
    path('management/', management_views.ManagementDashboardView.as_view(), name='management'),
    path('management/third-party-configs/', management_views.ThirdPartyConfigsView.as_view(), name='third_party_configs'),
    path('management/schedules/', management_views.TerminalSchedulesView.as_view(), name='schedules'),
    path('management/schedules/<int:terminal_id>/', management_views.TerminalSchedulesView.as_view(), name='schedules_terminal'),
    path('management/user-sync/', management_views.UserSyncView.as_view(), name='user_sync'),
    path('management/attendance-sync/', management_views.AttendanceSyncView.as_view(), name='attendance_sync'),
]
