from django.urls import path

from . import views

app_name = "statistiques"

urlpatterns = [
    path("", views.index, name="index"),
    path("produit/", views.par_produit, name="par_produit"),
    path("formation-sanitaire/", views.par_fosa, name="par_fosa"),
]
