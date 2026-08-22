from django.contrib import admin

from .models import Produit, Rayon


@admin.register(Rayon)
class RayonAdmin(admin.ModelAdmin):
    list_display = ("icone", "nom", "slug", "ordre")
    list_editable = ("ordre",)
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("code_sage", "nom", "unite", "prix_unitaire", "stock_disponible", "magasin", "rayon", "actif", "derniere_synchro")
    list_editable = ("prix_unitaire", "stock_disponible", "magasin", "rayon", "actif")
    list_filter = ("magasin", "rayon", "actif")
    search_fields = ("code_sage", "nom")
    readonly_fields = ("derniere_synchro",)
