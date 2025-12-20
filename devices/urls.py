"""
URLs API REST pour la gestion des terminaux (optionnel, pour l'admin)
"""

from django.urls import path

from . import views

app_name = 'devices'

urlpatterns = [
    path('terminals/', views.TerminalListView.as_view(), name='terminal-list'),
    path('terminals/<str:sn>/', views.TerminalDetailView.as_view(), name='terminal-detail'),
    path('terminals/<str:sn>/command/', views.SendCommandView.as_view(), name='terminal-command'),
    path('terminals/<str:sn>/users/', views.TerminalUsersView.as_view(), name='terminal-users'),
    path('terminals/<str:sn>/logs/', views.TerminalLogsView.as_view(), name='terminal-logs'),
    path('connected/', views.ConnectedTerminalsView.as_view(), name='connected-terminals'),
]
