"""
URLs v2 - Intégration du dashboard
"""

from django.contrib import admin
from django.urls import path, include
from .health import health_check

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/', include('devices.urls')),
    path('dashboard/', include('devices.dashboard.urls', namespace='dashboard')),
]
