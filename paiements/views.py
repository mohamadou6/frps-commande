from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import formation_sanitaire_required
from commandes.models import Commande, StatutCommande

from . import services
from .models import Paiement


@formation_sanitaire_required
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


@formation_sanitaire_required
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


@formation_sanitaire_required
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


@formation_sanitaire_required
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


@formation_sanitaire_required
def succes(request, commande_id):
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    return render(request, "paiements/succes.html", {"commande": commande})
