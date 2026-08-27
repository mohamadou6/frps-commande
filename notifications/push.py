import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

logger = logging.getLogger("notifications.push")

# Sans ce parametre, pywebpush envoie un TTL de 0s ("livrer maintenant ou
# abandonner") : un appareil hors ligne au moment de l'envoi ne recevrait
# jamais la notification, meme en se reconnectant ensuite - a l'oppose du
# SMS. 7 jours pour laisser le temps a un personnel absent le week-end.
_TTL_SECONDES = 7 * 24 * 60 * 60

# Un jeton d'abonnement qui n'existe plus cote navigateur continue d'etre accepte par
# FCM (201) sans jamais rien livrer : impossible de reperer ces abonnements fantomes a
# la reponse d'envoi. Le seul signal fiable est qu'ils ne sont plus reconfirmes, la
# page les reenregistrant a chaque affichage tant que l'appareil est vivant. Au-dela de
# ce delai on les supprime : un appareil bien vivant se reabonne des l'ouverture
# suivante, un fantome disparait definitivement.
_PEREMPTION_JOURS = 45


def _vapid():
    """py_vapid n'accepte pas directement une chaine PEM (voir Vapid.from_string,
    qui suppose du RAW/DER) : il faut construire l'objet Vapid01 via from_pem."""
    return Vapid01.from_pem(settings.VAPID_PRIVATE_KEY.encode())


def envoyer_push_a_abonnement(abonnement, titre, corps, url="/"):
    """Envoie une notification push à UN appareil.

    Retourne True si le service de push a accepté l'envoi — ce qui ne prouve pas la
    livraison (voir _PEREMPTION_JOURS). Un abonnement expiré/révoqué (404/410) est
    supprimé automatiquement."""
    if not settings.VAPID_PRIVATE_KEY:
        return False

    try:
        webpush(
            subscription_info={
                "endpoint": abonnement.endpoint,
                "keys": {"p256dh": abonnement.p256dh, "auth": abonnement.auth},
            },
            data=json.dumps({"titre": titre, "corps": corps, "url": url}),
            vapid_private_key=_vapid(),
            vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            ttl=_TTL_SECONDES,
            # Sans cet en-tete, pywebpush envoie une urgence "normal", qu'Android
            # traite comme un message de priorite normale : l'appareil en veille ne
            # le recoit qu'a sa prochaine fenetre de maintenance, soit plusieurs
            # dizaines de minutes de retard sur une commande a traiter.
            headers={"Urgency": "high"},
        )
        return True
    except WebPushException as exc:
        statut = exc.response.status_code if exc.response is not None else None
        if statut in (404, 410):
            abonnement.delete()
        else:
            logger.warning("Echec envoi push a %s: %s", abonnement.user, exc)
        return False


def envoyer_push_a_utilisateur(user, titre, corps, url="/"):
    """Envoie une notification push à tous les appareils abonnés de cet utilisateur.
    Silencieux si les clés VAPID ne sont pas configurées (dev local sans .env) ou si
    l'utilisateur n'a aucun abonnement."""
    if not settings.VAPID_PRIVATE_KEY:
        return

    limite = timezone.now() - timedelta(days=_PEREMPTION_JOURS)
    for abonnement in user.push_subscriptions.all():
        if abonnement.date_confirmation < limite:
            logger.info(
                "Abonnement push perime supprime (%s, derniere confirmation le %s)",
                user,
                abonnement.date_confirmation.date(),
            )
            abonnement.delete()
            continue
        envoyer_push_a_abonnement(abonnement, titre, corps, url=url)


def envoyer_push_aux_utilisateurs(users, titre, corps, url="/"):
    for user in users:
        envoyer_push_a_utilisateur(user, titre, corps, url=url)
