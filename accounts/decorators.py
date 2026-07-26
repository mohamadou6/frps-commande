from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Role


def formation_sanitaire_required(view_func):
    """Réservé aux formations sanitaires. L'admin FRPS a accès à tout (y compris
    ici) ; le personnel FRPS non-admin (stock/comptabilité) est redirigé vers ses
    notifications plutôt que de voir une erreur 403."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.is_formation_sanitaire or user.role == Role.ADMIN:
            return view_func(request, *args, **kwargs)
        return redirect("notifications:liste")

    return wrapper


def personnel_frps_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_formation_sanitaire:
            raise PermissionDenied("Réservé au personnel FRPS.")
        return view_func(request, *args, **kwargs)

    return wrapper


def formation_sanitaire_only_required(view_func):
    """Réservé aux comptes ayant un vrai profil FormationSanitaire (panier, commandes,
    paiements). Contrairement à formation_sanitaire_required, l'admin FRPS n'a PAS
    accès ici : il n'a pas de profil FormationSanitaire, ces vues planteraient sinon.
    Redirigé vers le catalogue (lecture seule) plutôt qu'une erreur."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.is_formation_sanitaire:
            return view_func(request, *args, **kwargs)
        if user.role == Role.ADMIN:
            return redirect("catalogue:liste")
        return redirect("notifications:liste")

    return wrapper
