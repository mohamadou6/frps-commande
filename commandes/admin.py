from django.contrib import admin

from .models import Commande, LigneCommande


class LigneCommandeInline(admin.TabularInline):
    model = LigneCommande
    extra = 0
    readonly_fields = ("produit", "quantite", "prix_unitaire_snapshot", "sous_total")
    can_delete = False


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ("id", "formation_sanitaire", "statut", "montant_total", "date_creation", "date_confirmation")
    list_filter = ("statut",)
    search_fields = ("formation_sanitaire__nom",)
    readonly_fields = ("montant_total", "date_creation", "date_confirmation")
    inlines = [LigneCommandeInline]
