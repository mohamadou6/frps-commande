from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


class LoginView(auth_views.LoginView):
    """Redirige après connexion selon le rôle : catalogue pour les formations
    sanitaires, notifications pour tout le reste du personnel FRPS (admin inclus)."""

    def get_success_url(self):
        if self.request.user.is_formation_sanitaire:
            return reverse_lazy("catalogue:liste")
        return reverse_lazy("notifications:liste")
