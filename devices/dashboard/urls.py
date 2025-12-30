"""
URLs du dashboard
"""

from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),
    path('api/', views.DashboardAPIView.as_view(), name='api'),
    path('api/terminals/', views.TerminalsAPIView.as_view(), name='terminals'),
    path('api/logs/', views.LogsAPIView.as_view(), name='logs'),
    path('api/events/', views.EventsAPIView.as_view(), name='events'),
    path('api/command/<str:sn>/', views.CommandAPIView.as_view(), name='command'),
]
