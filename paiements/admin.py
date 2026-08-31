from django.contrib import admin

from .models import Paiement, ReglementPaiement


class ReglementPaiementInline(admin.TabularInline):
    """Historique des versements d'une commande.

    Le montant et l'horodatage de saisie restent en lecture seule : ce sont des faits.
    `date_paiement` et `methode` sont volontairement modifiables — une date de règlement
    est saisie à la main, souvent après coup, donc corrigible en cas d'erreur.
    """

    model = ReglementPaiement
    extra = 0
    fields = ("montant", "date_paiement", "methode", "date_reglement", "saisi_par")
    readonly_fields = ("montant", "date_reglement", "saisi_par")
    can_delete = False


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ("commande", "methode", "montant", "montant_paye", "statut", "reference_transaction", "date_initiation")
    list_filter = ("methode", "statut")
    search_fields = ("reference_transaction", "commande__formation_sanitaire__nom")
    readonly_fields = ("date_initiation",)
    actions = ["confirmer_paiements_selectionnes"]
    inlines = [ReglementPaiementInline]

    @admin.action(description="Confirmer le paiement (mode test/mock)")
    def confirmer_paiements_selectionnes(self, request, queryset):
        from .services import confirmer_paiement

        for paiement in queryset:
            confirmer_paiement(paiement, succes=True)
