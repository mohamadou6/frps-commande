import json
import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection
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

# pywebpush n'impose aucun delai maximum a l'appel reseau : un service de push qui ne
# repond pas gele l'appel indefiniment. Mesure le 2026-08-29 depuis un reseau lent :
# 37 s pour un seul appareil. Ces envois partant depuis la requete de confirmation de
# commande, sans cette borne c'est la FOSA qui attend - puis la requete qui est coupee.
_DELAI_ENVOI_SECONDES = 10


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
            timeout=_DELAI_ENVOI_SECONDES,
        )
        _tracer(abonnement, "envoyé")
        return True
    except WebPushException as exc:
        statut = exc.response.status_code if exc.response is not None else None
        if statut in (404, 410):
            abonnement.delete()
        else:
            logger.warning("Echec envoi push a %s: %s", abonnement.user, exc)
            _tracer(abonnement, f"echec {statut or 'reseau'}")
        return False
    except Exception as exc:  # noqa: BLE001 - delai depasse, DNS, coupure reseau
        logger.warning("Echec envoi push a %s: %s", abonnement.user, exc)
        _tracer(abonnement, "injoignable")
        return False


def _tracer(abonnement, statut):
    """Garde la trace du dernier envoi, affichée dans « Mes appareils ».

    Écriture par `update()` : un `save()` déclencherait l'`auto_now` de
    `date_confirmation` et ferait passer un abonnement fantôme pour vivant, ce qui
    désamorcerait la péremption."""
    from .models import PushSubscription

    PushSubscription.objects.filter(pk=abonnement.pk).update(
        date_dernier_envoi=timezone.now(), dernier_statut=statut
    )


def _envoyer_aux_abonnements(abonnements, titre, corps, url):
    limite = timezone.now() - timedelta(days=_PEREMPTION_JOURS)
    for abonnement in abonnements:
        if abonnement.date_confirmation < limite:
            logger.info(
                "Abonnement push perime supprime (%s, derniere confirmation le %s)",
                abonnement.user,
                abonnement.date_confirmation.date(),
            )
            abonnement.delete()
            continue
        envoyer_push_a_abonnement(abonnement, titre, corps, url=url)


def envoyer_push_a_utilisateur(user, titre, corps, url="/"):
    """Envoie une notification push à tous les appareils abonnés de cet utilisateur.
    Silencieux si les clés VAPID ne sont pas configurées (dev local sans .env) ou si
    l'utilisateur n'a aucun abonnement."""
    if not settings.VAPID_PRIVATE_KEY:
        return

    _envoyer_aux_abonnements(list(user.push_subscriptions.all()), titre, corps, url)


def envoyer_push_aux_utilisateurs(users, titre, corps, url="/"):
    """Envoi en tâche de fond : ces notifications partent depuis la requête de
    confirmation de commande, et un service de push lent ferait attendre la FOSA
    pour un envoi dont elle n'est même pas destinataire. Le fil est détaché — une
    notification perdue en cas de redémarrage du serveur est un moindre mal comparé
    à une commande qui n'aboutit pas, et le SMS reste la voie garantie."""
    if not settings.VAPID_PRIVATE_KEY:
        return

    # Les abonnements sont lus ICI, dans le fil de la requête : le fil détaché ne fait
    # plus que du réseau, il n'a pas à rouvrir de connexion pour savoir à qui écrire.
    from .models import PushSubscription

    abonnements = list(PushSubscription.objects.filter(user__in=users).select_related("user"))
    if not abonnements:
        return

    threading.Thread(
        target=_envoyer_en_tache_de_fond, args=(abonnements, titre, corps, url), daemon=True
    ).start()


def _envoyer_en_tache_de_fond(abonnements, titre, corps, url):
    try:
        _envoyer_aux_abonnements(abonnements, titre, corps, url)
    except Exception:  # noqa: BLE001 - un fil detache ne doit jamais remonter d'exception
        logger.exception("Echec de l'envoi push en tache de fond")
    finally:
        # Le fil ouvre sa propre connexion des qu'il ecrit (trace d'envoi, suppression
        # d'un abonnement revoque) : sans cette fermeture, elles s'accumuleraient
        # jusqu'a saturer le pool de connexions Postgres.
        connection.close()
