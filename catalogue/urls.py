from django.urls import path

from . import views, views_espace

app_name = "catalogue"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("importer/", views.importer_produits, name="importer"),
    path("promotions/", views.promotions, name="promotions"),
    path("promotions/gerer/", views.gerer_promotions, name="gerer_promotions"),
    path("promotions/<int:promotion_id>/arreter/", views.arreter_promotion, name="arreter_promotion"),
    path("promotions/baisse/<int:produit_id>/masquer/", views.masquer_baisse, name="masquer_baisse"),
    # Espace FOSA
    path("alertes/", views_espace.alertes, name="alertes"),
    path("alertes/<int:produit_id>/demander/", views_espace.demander_alerte, name="demander_alerte"),
    path("alertes/<int:produit_id>/annuler/", views_espace.annuler_alerte, name="annuler_alerte"),
    path("habituels/", views_espace.habituels, name="habituels"),
    path("habituels/<int:produit_id>/basculer/", views_espace.basculer_habituel, name="basculer_habituel"),
    path("habituels/preremplir/", views_espace.preremplir_habituels, name="preremplir_habituels"),
    path("habituels/commande-mensuelle/", views_espace.programmer_commande, name="programmer_commande"),
]
