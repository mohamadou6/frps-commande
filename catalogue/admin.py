from django.contrib import admin

from .models import Produit


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("code_sage", "nom", "unite", "prix_unitaire", "stock_disponible", "actif", "derniere_synchro")
    list_editable = ("prix_unitaire", "stock_disponible", "actif")
    list_filter = ("actif",)
    search_fields = ("code_sage", "nom")
    readonly_fields = ("derniere_synchro",)
