from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("<int:notification_id>/lu/", views.marquer_lu, name="marquer_lu"),
    path("tout-lu/", views.marquer_tout_lu, name="marquer_tout_lu"),
    path("abonnement-push/", views.enregistrer_abonnement_push, name="abonnement_push"),
    path("abonnement-push/<int:abonnement_id>/test/", views.tester_abonnement_push, name="tester_abonnement_push"),
    path(
        "abonnement-push/<int:abonnement_id>/supprimer/",
        views.supprimer_abonnement_push,
        name="supprimer_abonnement_push",
    ),
    path("parametres/emails/", views.parametres_emails, name="parametres_emails"),
    path(
        "parametres/emails/<int:destinataire_id>/modifier/",
        views.modifier_destinataire_email,
        name="modifier_destinataire_email",
    ),
    path(
        "parametres/emails/<int:destinataire_id>/supprimer/",
        views.supprimer_destinataire_email,
        name="supprimer_destinataire_email",
    ),
    path(
        "parametres/emails/<int:destinataire_id>/tester/",
        views.tester_destinataire_email,
        name="tester_destinataire_email",
    ),
    path("orange-dr/", views.orange_dr_callback, name="orange_dr_callback"),
    path("twilio-dlr/", views.twilio_status_callback, name="twilio_status_callback"),
]
