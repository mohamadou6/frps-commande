# Le paiement en ligne (Orange Money / espèces initiés par la FOSA) reste en pause
# depuis le retrait de l'étape paiement du parcours FOSA (2026-07-26) :
# confirmer_commande (commandes/views.py) mène directement au détail de la commande,
# aucun lien de l'UI FOSA ne pointe vers payer/initier/payer_especes/confirmer_mock
# ci-dessous (gardées pour un usage futur si cette étape est réintroduite).
#
# En revanche, depuis le 2026-07-31, le personnel comptabilité FRPS peut saisir
# manuellement l'état de paiement d'une commande payée hors application (espèces
# remises physiquement) via gerer_paiements/modifier_paiement ci-dessous — la FOSA le
# voit ensuite en lecture seule sur le détail de sa commande, et le personnel stock
# voit aussi la liste en lecture seule (pas d'accès à la modification).
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import (
    comptabilite_frps_required,
    formation_sanitaire_only_required,
    personnel_frps_required,
)
from commandes.models import Commande, StatutCommande

from . import services
from .models import Paiement


@formation_sanitaire_only_required
def payer(request, commande_id):
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    if commande.statut == StatutCommande.BROUILLON:
        messages.error(request, "Cette commande doit d'abord être confirmée.")
        return redirect("commandes:panier")

    paiement = Paiement.objects.filter(commande=commande).first()
    return render(
        request,
        "paiements/payer.html",
        {
            "commande": commande,
            "paiement": paiement,
            "orange_money_compte": settings.ORANGE_MONEY_COMPTE_FRPS,
        },
    )


@formation_sanitaire_only_required
@require_POST
def initier(request, commande_id):
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    try:
        services.initier_paiement(commande)
        messages.success(request, "Paiement Orange Money initié.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("paiements:payer", commande_id=commande.pk)


@formation_sanitaire_only_required
@require_POST
def payer_especes(request, commande_id):
    """Valide la commande en paiement espèces : aucune étape supplémentaire."""
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    try:
        services.payer_en_especes(commande)
        messages.success(
            request,
            "Commande validée en paiement espèces. Le FRPS a été notifié par SMS pour l'édition du reçu.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("paiements:payer", commande_id=commande.pk)
    return redirect("paiements:succes", commande_id=commande.pk)


@formation_sanitaire_only_required
@require_POST
def confirmer_mock(request, commande_id):
    """Simule le callback Orange Money (uniquement utile en mode mock/démo)."""
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    paiement = get_object_or_404(Paiement, commande=commande)
    services.confirmer_paiement(paiement, succes=True)
    messages.success(
        request,
        "Paiement confirmé. Le FRPS a été notifié par SMS pour l'édition du reçu.",
    )
    return redirect("paiements:succes", commande_id=commande.pk)


@formation_sanitaire_only_required
def succes(request, commande_id):
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    return render(request, "paiements/succes.html", {"commande": commande})


@personnel_frps_required
def gerer_paiements(request):
    """Liste consultable par tout le personnel FRPS (stock inclus, en lecture) ; seule
    la modification (modifier_paiement) reste réservée à comptabilité/admin."""
    query = request.GET.get("q", "").strip()
    commandes = (
        Commande.objects.filter(statut__in=[StatutCommande.CONFIRMEE, StatutCommande.PAYEE])
        .select_related("formation_sanitaire", "paiement")
        .order_by("-date_confirmation")
    )
    if query:
        commandes = commandes.filter(formation_sanitaire__nom__icontains=query)
    return render(request, "paiements/gerer.html", {"commandes": commandes, "query": query})


@comptabilite_frps_required
def modifier_paiement(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    if request.method == "POST":
        try:
            montant_paye = services.mettre_a_jour_paiement(commande, request.POST.get("montant_paye"), request.user)
            messages.success(request, f"État de paiement mis à jour : {montant_paye} FCFA reçus.")
            return redirect("paiements:gerer_paiements")
        except ValueError as exc:
            messages.error(request, str(exc))
    return render(request, "paiements/modifier.html", {"commande": commande})
