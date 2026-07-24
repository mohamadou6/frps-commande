from django.contrib import admin

from .models import Paiement


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ("commande", "methode", "montant", "statut", "reference_transaction", "date_initiation")
    list_filter = ("methode", "statut")
    search_fields = ("reference_transaction", "commande__formation_sanitaire__nom")
    readonly_fields = ("date_initiation",)
    actions = ["confirmer_paiements_selectionnes"]

    @admin.action(description="Confirmer le paiement (mode test/mock)")
    def confirmer_paiements_selectionnes(self, request, queryset):
        from .services import confirmer_paiement

        for paiement in queryset:
            confirmer_paiement(paiement, succes=True)
