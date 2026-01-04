"""
URLs v2 - Architecture refactorée
"""

from django.urls import path, include

from . import views
from .dashboard import urls as dashboard_urls
from .api import urls as api_urls_v2

app_name = 'devices'

urlpatterns = [
    # API REST pour les terminaux
    path('terminals/', views.TerminalListView.as_view(), name='terminal-list'),
    path('terminals/<str:sn>/', views.TerminalDetailView.as_view(), name='terminal-detail'),
    path('terminals/<str:sn>/command/', views.SendCommandView.as_view(), name='terminal-command'),
    path('terminals/<str:sn>/users/', views.TerminalUsersView.as_view(), name='terminal-users'),
    path('terminals/<str:sn>/logs/', views.TerminalLogsView.as_view(), name='terminal-logs'),
    path('connected/', views.ConnectedTerminalsView.as_view(), name='connected-terminals'),
    
    # API REST v2 pour gestion avancée (services tiers, sync, horaires)
    path('api/', include(api_urls_v2, namespace='api')),
    
    # Dashboard
    path('dashboard/', include(dashboard_urls, namespace='dashboard')),
]
