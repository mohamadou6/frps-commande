from django.urls import path

from . import views

app_name = "commandes"

urlpatterns = [
    path("", views.panier, name="panier"),
    path("ajouter/<int:produit_id>/", views.ajouter, name="ajouter"),
    path("modifier-quantite/<int:produit_id>/", views.modifier_quantite, name="modifier_quantite"),
    path("retirer/<int:produit_id>/", views.retirer, name="retirer"),
    path("confirmer/", views.confirmer, name="confirmer"),
    path("demandes/synchroniser/", views.synchroniser_demande, name="synchroniser_demande"),
    path("historique/", views.historique, name="historique"),
    path("suivi/", views.suivi, name="suivi"),
    path("<int:commande_id>/etape/", views.avancer_etape, name="avancer_etape"),
    path("<int:commande_id>/recommander/", views.recommander, name="recommander"),
    path("<int:commande_id>/pdf/<str:token>/", views.pdf_commande, name="pdf"),
    path("<int:commande_id>/telecharger/", views.telecharger_pdf, name="telecharger_pdf"),
    path("<int:commande_id>/telecharger-staff/", views.telecharger_pdf_staff, name="telecharger_pdf_staff"),
    path("<int:commande_id>/supprimer/", views.supprimer, name="supprimer"),
    path("<int:commande_id>/", views.detail, name="detail"),
]
