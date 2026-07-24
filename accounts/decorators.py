from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def formation_sanitaire_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_formation_sanitaire:
            raise PermissionDenied("Réservé aux formations sanitaires.")
        return view_func(request, *args, **kwargs)

    return wrapper


def personnel_frps_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_formation_sanitaire:
            raise PermissionDenied("Réservé au personnel FRPS.")
        return view_func(request, *args, **kwargs)

    return wrapper
