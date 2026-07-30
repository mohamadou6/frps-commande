from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache


@method_decorator(never_cache, name="dispatch")
class LoginView(auth_views.LoginView):
    """Redirige après connexion selon le rôle : catalogue pour les formations
    sanitaires, tableau de bord (statistiques) pour tout le reste du personnel FRPS
    (admin inclus).

    never_cache empêche le navigateur (surtout mobile) de resservir une page de
    connexion mise en cache avec un jeton CSRF périmé — cause du 403 "CSRF
    verification failed" observé à la première connexion tant que la page
    n'était pas rechargée manuellement."""

    def get_success_url(self):
        if self.request.user.is_formation_sanitaire:
            return reverse_lazy("catalogue:liste")
        return reverse_lazy("statistiques:index")
