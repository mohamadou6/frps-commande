from django.contrib import admin

from .models import BaissePrix, Produit, Rayon
from .services import noter_baisses_prix


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

    def save_model(self, request, obj, form, change):
        # Prix baissé à la main (fiche ou liste éditable) : il doit apparaître dans
        # les Promotions des FOSA comme une baisse venue de l'import Excel.
        ancien_prix = form.initial.get("prix_unitaire") if change else None
        super().save_model(request, obj, form, change)
        if change and "prix_unitaire" in form.changed_data and ancien_prix is not None:
            noter_baisses_prix([(obj, ancien_prix, obj.prix_unitaire)])


@admin.register(BaissePrix)
class BaissePrixAdmin(admin.ModelAdmin):
    """Aussi visible dans l'application : Administration > Promotions."""

    list_display = ("produit", "ancien_prix", "nouveau_prix", "date", "visible")
    list_editable = ("visible",)
    list_filter = ("visible",)
    search_fields = ("produit__nom", "produit__code_sage")
    raw_id_fields = ("produit",)
    readonly_fields = ("date",)
