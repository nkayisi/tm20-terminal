"""
URLs v2 - Intégration du dashboard
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.shortcuts import redirect
from django.http import HttpResponseRedirect
from .health import health_check


def root_redirect(request):
    """Redirection racine vers login ou dashboard selon l'état d'authentification"""
    if request.user.is_authenticated:
        return HttpResponseRedirect('/dashboard/')
    else:
        return HttpResponseRedirect('/login/')


class CustomLoginView(auth_views.LoginView):
    """Vue de login personnalisée avec redirection automatique"""
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('/dashboard/')
        return super().dispatch(request, *args, **kwargs)

urlpatterns = [
    # Authentication
    path('', root_redirect, name='root'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/', include('devices.urls')),
    path('dashboard/', include('devices.dashboard.urls', namespace='dashboard')),
]
