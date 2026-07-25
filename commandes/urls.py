from django.urls import path

from . import views

app_name = "commandes"

urlpatterns = [
    path("", views.panier, name="panier"),
    path("ajouter/<int:produit_id>/", views.ajouter, name="ajouter"),
    path("retirer/<int:produit_id>/", views.retirer, name="retirer"),
    path("confirmer/", views.confirmer, name="confirmer"),
    path("historique/", views.historique, name="historique"),
    path("<int:commande_id>/pdf/<str:token>/", views.pdf_commande, name="pdf"),
    path("<int:commande_id>/telecharger/", views.telecharger_pdf, name="telecharger_pdf"),
    path("<int:commande_id>/telecharger-staff/", views.telecharger_pdf_staff, name="telecharger_pdf_staff"),
    path("<int:commande_id>/", views.detail, name="detail"),
]
