import json
import logging

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import personnel_frps_required
from accounts.models import Role

from .models import Notification, PushSubscription, SMSLog
from .push import envoyer_push_a_abonnement

logger = logging.getLogger("notifications.sms")


def _notifications_du_role(user):
    if user.role == Role.ADMIN:
        return Notification.objects.all()
    return Notification.objects.filter(role_cible=user.role)


@personnel_frps_required
def liste(request):
    notifications = _notifications_du_role(request.user).select_related("commande")
    return render(
        request,
        "notifications/liste.html",
        {
            "notifications": notifications,
            "abonnements_push": request.user.push_subscriptions.order_by("-date_confirmation"),
        },
    )


@personnel_frps_required
@require_POST
def marquer_lu(request, notification_id):
    notification = get_object_or_404(_notifications_du_role(request.user), pk=notification_id)
    notification.lu = True
    notification.save(update_fields=["lu"])
    return redirect("notifications:liste")


@personnel_frps_required
@require_POST
def marquer_tout_lu(request):
    _notifications_du_role(request.user).filter(lu=False).update(lu=True)
    messages.success(request, "Notifications marquées comme lues.")
    return redirect("notifications:liste")


@personnel_frps_required
@require_POST
def enregistrer_abonnement_push(request):
    """Reçoit l'abonnement Web Push créé côté navigateur (PushManager.subscribe)
    et le rattache à l'utilisateur connecté. Réservé au personnel FRPS : les
    FOSA n'ont pas accès aux notifications push (voir notifications/push.py).

    Le navigateur fait tourner le jeton d'abonnement sans prévenir : sans ménage,
    la base accumulait un abonnement fantôme par rotation, accepté par FCM (201)
    mais ne livrant plus rien — l'utilisateur ne recevait la notification que sur
    l'appareil dont le jeton était encore vivant. On supprime donc l'abonnement
    précédent du même appareil, identifié soit par `ancien_endpoint` (envoyé par
    le service worker sur `pushsubscriptionchange`), soit par `appareil_id`
    (identifiant stable stocké dans le localStorage, envoyé par la page)."""
    try:
        payload = json.loads(request.body or b"{}")
        endpoint = payload["endpoint"]
        p256dh = payload["keys"]["p256dh"]
        auth = payload["keys"]["auth"]
    except (ValueError, KeyError):
        return HttpResponse(status=400)

    appareil_id = str(payload.get("appareil_id") or "")[:64]
    ancien_endpoint = str(payload.get("ancien_endpoint") or "")

    conditions = Q()
    if appareil_id:
        conditions |= Q(user=request.user, appareil_id=appareil_id)
    if ancien_endpoint:
        conditions |= Q(endpoint=ancien_endpoint)
    if conditions:
        perimes, _ = PushSubscription.objects.filter(conditions).exclude(endpoint=endpoint).delete()
        if perimes:
            logger.info("Push: %s abonnement(s) perime(s) remplace(s) pour %s", perimes, request.user)

    valeurs = {"user": request.user, "p256dh": p256dh, "auth": auth}
    if appareil_id:
        # Jamais d'écrasement par une chaîne vide : le service worker, lui, n'a pas
        # accès au localStorage et ne peut pas fournir cet identifiant.
        valeurs["appareil_id"] = appareil_id
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults=valeurs)
    return HttpResponse(status=204)


@personnel_frps_required
@require_POST
def tester_abonnement_push(request, abonnement_id):
    """Envoie une notification de test à UN appareil de l'utilisateur connecté.
    Seul moyen de savoir quel appareil reçoit réellement : une acceptation par le
    service de push ne prouve pas la livraison."""
    abonnement = get_object_or_404(PushSubscription, pk=abonnement_id, user=request.user)
    if envoyer_push_a_abonnement(
        abonnement,
        "Test de notification",
        "Si vous lisez ceci, cet appareil reçoit bien les notifications FRPS.",
        url="/notifications/",
    ):
        messages.success(
            request,
            "Notification de test envoyée. Si elle n'arrive pas sur cet appareil dans "
            "la minute, supprimez l'abonnement : il est périmé.",
        )
    else:
        messages.error(request, "L'envoi a échoué : abonnement supprimé ou clés push non configurées.")
    return redirect("notifications:liste")


@personnel_frps_required
@require_POST
def supprimer_abonnement_push(request, abonnement_id):
    abonnement = get_object_or_404(PushSubscription, pk=abonnement_id, user=request.user)
    abonnement.delete()
    messages.success(
        request, "Appareil retiré. Rouvrez l'application sur cet appareil pour le réabonner."
    )
    return redirect("notifications:liste")


@csrf_exempt
@require_POST
def orange_dr_callback(request):
    """Reçoit le Delivery Receipt (DR) envoyé par Orange après l'envoi d'un SMS via
    OrangeSMSBackend (voir notifications/backends.py) : c'est le SEUL moyen fiable
    de savoir si un SMS a réellement été livré (un 201 à l'envoi ne le garantit pas).

    URL publique, sans authentification Django (Orange ne fournit ni session ni
    signature documentée) — doit être déclarée à Orange via leur formulaire de
    configuration DR une fois l'appli déployée (URL HTTPS publique requise, pas
    d'équivalent possible en local). Toujours répondre 200 pour accuser réception.

    Payload attendu (doc Orange) :
        {"deliveryInfoNotification": {"callbackData": "<resource_id>",
         "deliveryInfo": {"address": "tel:+237...", "deliveryStatus": "..."}}}
    """
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        logger.warning("Orange DR callback: corps de requete illisible: %r", request.body[:500])
        return HttpResponse(status=200)

    notification = payload.get("deliveryInfoNotification") or {}
    resource_id = notification.get("callbackData") or ""
    delivery_info = notification.get("deliveryInfo") or {}
    statut = delivery_info.get("deliveryStatus") or ""
    adresse = delivery_info.get("address") or ""

    logger.info("Orange DR callback: resource_id=%s adresse=%s statut=%s", resource_id, adresse, statut)

    if resource_id:
        maj = SMSLog.objects.filter(reference_externe=resource_id).update(
            statut_livraison=statut, date_statut_livraison=timezone.now()
        )
        if not maj:
            logger.warning("Orange DR callback: aucun SMSLog trouve pour resource_id=%s", resource_id)

    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def twilio_status_callback(request):
    """Reçoit l'accusé de livraison (DLR) envoyé par Twilio après chaque SMS.

    Sans ce callback, SMSLog.statut_livraison restait vide pour Twilio et
    l'application affichait « envoyé » même quand l'opérateur destinataire ne
    livrait jamais le message — c'est ainsi qu'une dégradation de route vers le
    Cameroun est passée inaperçue plusieurs jours en août 2026.

    URL publique, sans authentification Django (Twilio ne fournit pas de session) :
    à déclarer dans la console Twilio ou, comme ici, passée à chaque envoi via
    `status_callback`. Toujours répondre 200 pour accuser réception.

    Twilio poste en form-encoded : MessageSid, MessageStatus, ErrorCode.
    """
    sid = request.POST.get("MessageSid") or ""
    statut = request.POST.get("MessageStatus") or ""
    code_erreur = request.POST.get("ErrorCode") or ""

    logger.info("Twilio DLR: sid=%s statut=%s erreur=%s", sid, statut, code_erreur)

    if sid:
        maj = SMSLog.objects.filter(reference_externe=sid).update(
            statut_livraison=statut, date_statut_livraison=timezone.now()
        )
        if not maj:
            logger.warning("Twilio DLR: aucun SMSLog trouve pour sid=%s", sid)

    return HttpResponse(status=200)
