from django.conf import settings

from accounts.models import Role

from .models import Notification


def notifications_non_lues(request):
    """Expose le nombre de notifications non lues du personnel FRPS connecté,
    pour afficher un badge dans la navbar sur toutes les pages, ainsi que la clé
    publique VAPID (nécessaire côté navigateur pour s'abonner au push)."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    if user.is_formation_sanitaire:
        # Depuis le 2026-11-19, les FOSA reçoivent aussi des notifications push
        # (commande prête, retour en stock, réponse à une réclamation…) : elles ont
        # besoin de la clé pour s'abonner, pas du compteur de notifications internes.
        if user.fiche_fosa is None:
            return {}
        return {"vapid_public_key": settings.VAPID_PUBLIC_KEY}

    if user.role == Role.ADMIN:
        compte = Notification.objects.filter(lu=False).count()
    else:
        compte = Notification.objects.filter(role_cible=user.role, lu=False).count()

    return {"notifications_non_lues_count": compte, "vapid_public_key": settings.VAPID_PUBLIC_KEY}
