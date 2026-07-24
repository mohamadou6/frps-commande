from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import personnel_frps_required
from accounts.models import Role

from .models import Notification


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
