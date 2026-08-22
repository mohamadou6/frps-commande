import json
import logging

from django.conf import settings
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

logger = logging.getLogger("notifications.push")


def _vapid():
    """py_vapid n'accepte pas directement une chaine PEM (voir Vapid.from_string,
    qui suppose du RAW/DER) : il faut construire l'objet Vapid01 via from_pem."""
    return Vapid01.from_pem(settings.VAPID_PRIVATE_KEY.encode())


def envoyer_push_a_utilisateur(user, titre, corps, url="/"):
    """Envoie une notification push à tous les appareils abonnés de cet utilisateur.
    Silencieux si les clés VAPID ne sont pas configurées (dev local sans .env) ou si
    l'utilisateur n'a aucun abonnement. Un abonnement expiré/révoqué (410/404) est
    supprimé automatiquement."""
    if not settings.VAPID_PRIVATE_KEY:
        return

    charge_utile = json.dumps({"titre": titre, "corps": corps, "url": url})
    vapid = _vapid()

    for abonnement in user.push_subscriptions.all():
        subscription_info = {
            "endpoint": abonnement.endpoint,
            "keys": {"p256dh": abonnement.p256dh, "auth": abonnement.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=charge_utile,
                vapid_private_key=vapid,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            )
        except WebPushException as exc:
            statut = exc.response.status_code if exc.response is not None else None
            if statut in (404, 410):
                abonnement.delete()
            else:
                logger.warning("Echec envoi push a %s: %s", user, exc)


def envoyer_push_aux_utilisateurs(users, titre, corps, url="/"):
    for user in users:
        envoyer_push_a_utilisateur(user, titre, corps, url=url)
