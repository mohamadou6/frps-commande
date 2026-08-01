from django.urls import path

from . import views

app_name = "paiements"

urlpatterns = [
    path("gerer/", views.gerer_paiements, name="gerer_paiements"),
    path("<int:commande_id>/", views.payer, name="payer"),
    path("<int:commande_id>/initier/", views.initier, name="initier"),
    path("<int:commande_id>/especes/", views.payer_especes, name="payer_especes"),
    path("<int:commande_id>/confirmer-mock/", views.confirmer_mock, name="confirmer_mock"),
    path("<int:commande_id>/succes/", views.succes, name="succes"),
    path("<int:commande_id>/modifier/", views.modifier_paiement, name="modifier_paiement"),
]
