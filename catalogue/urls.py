from django.urls import path

from . import views

app_name = "catalogue"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("importer/", views.importer_produits, name="importer"),
    path("promotions/", views.promotions, name="promotions"),
    path("promotions/gerer/", views.gerer_promotions, name="gerer_promotions"),
    path("promotions/<int:promotion_id>/arreter/", views.arreter_promotion, name="arreter_promotion"),
    path("promotions/baisse/<int:produit_id>/masquer/", views.masquer_baisse, name="masquer_baisse"),
]
