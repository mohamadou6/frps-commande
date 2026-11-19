from django.contrib import admin

from .models import AlerteStock, BaissePrix, CommandeMensuelle, Produit, ProduitHabituel, Promotion, Rayon
from .espace_fosa import traiter_retours_en_stock
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
        # Stock remis à la main : prévenir les FOSA qui attendaient ce produit.
        if "stock_disponible" in form.changed_data or "actif" in form.changed_data:
            traiter_retours_en_stock()


@admin.register(BaissePrix)
class BaissePrixAdmin(admin.ModelAdmin):
    """Aussi visible dans l'application : Administration > Promotions."""

    list_display = ("produit", "ancien_prix", "nouveau_prix", "date", "visible")
    list_editable = ("visible",)
    list_filter = ("visible",)
    search_fields = ("produit__nom", "produit__code_sage")
    raw_id_fields = ("produit",)
    readonly_fields = ("date",)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    """Aussi gérable dans l'application : Administration > Créer une promotion."""

    list_display = ("produit", "prix_promotionnel", "date_debut", "date_fin", "active", "creee_par")
    list_filter = ("active",)
    search_fields = ("produit__nom",)
    raw_id_fields = ("produit",)


@admin.register(AlerteStock)
class AlerteStockAdmin(admin.ModelAdmin):
    """Demandes de retour en stock : montre au FRPS les ruptures les plus attendues."""

    list_display = ("produit", "formation_sanitaire", "date_demande", "date_notification")
    list_filter = ("date_notification",)
    search_fields = ("produit__nom", "formation_sanitaire__nom")
    raw_id_fields = ("produit", "formation_sanitaire")


@admin.register(ProduitHabituel)
class ProduitHabituelAdmin(admin.ModelAdmin):
    list_display = ("formation_sanitaire", "produit", "quantite")
    search_fields = ("produit__nom", "formation_sanitaire__nom")
    raw_id_fields = ("produit", "formation_sanitaire")


@admin.register(CommandeMensuelle)
class CommandeMensuelleAdmin(admin.ModelAdmin):
    list_display = ("formation_sanitaire", "jour_du_mois", "active", "dernier_mois_prepare")
    list_filter = ("active",)
