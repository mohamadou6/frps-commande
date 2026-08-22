from django.conf import settings

from accounts.models import Role

from .models import Notification


def notifications_non_lues(request):
    """Expose le nombre de notifications non lues du personnel FRPS connecté,
    pour afficher un badge dans la navbar sur toutes les pages, ainsi que la clé
    publique VAPID (nécessaire côté navigateur pour s'abonner au push)."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.is_formation_sanitaire:
        return {}

    if user.role == Role.ADMIN:
        compte = Notification.objects.filter(lu=False).count()
    else:
        compte = Notification.objects.filter(role_cible=user.role, lu=False).count()

    return {"notifications_non_lues_count": compte, "vapid_public_key": settings.VAPID_PUBLIC_KEY}
