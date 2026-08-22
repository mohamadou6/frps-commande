import json
import logging

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import personnel_frps_required
from accounts.models import Role

from .models import Notification, PushSubscription, SMSLog

logger = logging.getLogger("notifications.sms")


def _notifications_du_role(user):
    if user.role == Role.ADMIN:
        return Notification.objects.all()
    return Notification.objects.filter(role_cible=user.role)


@personnel_frps_required
def liste(request):
    notifications = _notifications_du_role(request.user).select_related("commande")
    return render(request, "notifications/liste.html", {"notifications": notifications})


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
    et le rattache à l'utilisateur connecté, pour lui envoyer des notifications
    push (voir notifications/push.py)."""
    try:
        payload = json.loads(request.body or b"{}")
        endpoint = payload["endpoint"]
        p256dh = payload["keys"]["p256dh"]
        auth = payload["keys"]["auth"]
    except (ValueError, KeyError):
        return HttpResponse(status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint, defaults={"user": request.user, "p256dh": p256dh, "auth": auth}
    )
    return HttpResponse(status=204)


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
