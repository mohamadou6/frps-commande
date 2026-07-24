from django.contrib import admin

from .models import Produit


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("code_sage", "nom", "unite", "prix_unitaire", "stock_disponible", "magasin", "actif", "derniere_synchro")
    list_editable = ("prix_unitaire", "stock_disponible", "magasin", "actif")
    list_filter = ("magasin", "actif")
    search_fields = ("code_sage", "nom")
    readonly_fields = ("derniere_synchro",)
