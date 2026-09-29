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

    def form_valid(self, form):
        """Honore la case « Se souvenir de moi » du formulaire.

        La case existait dans le gabarit et était postée, mais rien ne la
        lisait : la session durait `SESSION_COOKIE_AGE` dans tous les cas.
        Décochée, la session expire désormais à la fermeture du navigateur.
        """
        if not self.request.POST.get('remember'):
            self.request.session.set_expiry(0)
        return super().form_valid(form)

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
