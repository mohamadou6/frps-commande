from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("<int:notification_id>/lu/", views.marquer_lu, name="marquer_lu"),
    path("tout-lu/", views.marquer_tout_lu, name="marquer_tout_lu"),
    path("abonnement-push/", views.enregistrer_abonnement_push, name="abonnement_push"),
    path("orange-dr/", views.orange_dr_callback, name="orange_dr_callback"),
    path("twilio-dlr/", views.twilio_status_callback, name="twilio_status_callback"),
]
