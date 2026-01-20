"""
Vue de login personnalisée avec redirection automatique pour les utilisateurs connectés
"""

from django.contrib.auth import views as auth_views
from django.shortcuts import redirect


class CustomLoginView(auth_views.LoginView):
    """
    Vue de login personnalisée qui redirige automatiquement 
    les utilisateurs déjà connectés vers le dashboard
    """
    
    def dispatch(self, request, *args, **kwargs):
        # Si l'utilisateur est déjà connecté, le rediriger vers le dashboard
        if request.user.is_authenticated:
            return redirect('/dashboard/')
        
        # Sinon, afficher la page de login normale
        return super().dispatch(request, *args, **kwargs)
