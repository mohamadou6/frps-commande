from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import formation_sanitaire_only_required, personnel_frps_required
from catalogue.models import Produit
from notifications.pdf import generer_pdf_commande, verifier_token_pdf

from . import services
from .models import Commande, StatutCommande


@formation_sanitaire_only_required
def panier(request):
    commande = services.get_panier(request.user.formation_sanitaire)
    return render(request, "commandes/panier.html", {"commande": commande})


@formation_sanitaire_only_required
@require_POST
def ajouter(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id, actif=True)
    commande = services.get_panier(request.user.formation_sanitaire)
    try:
        quantite = int(request.POST.get("quantite", "1"))
        services.ajouter_produit(commande, produit, quantite)
        messages.success(request, f"{produit.nom} ajouté au panier.")
    except (services.StockInsuffisantError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("catalogue:liste")


@formation_sanitaire_only_required
@require_POST
def retirer(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id)
    commande = services.get_panier(request.user.formation_sanitaire)
    services.retirer_produit(commande, produit)
    messages.success(request, f"{produit.nom} retiré du panier.")
    return redirect("commandes:panier")


@formation_sanitaire_only_required
@require_POST
def confirmer(request):
    commande = services.get_panier(request.user.formation_sanitaire)
    try:
        services.confirmer_commande(commande)
        messages.success(request, "Commande confirmée. Le FRPS a été notifié par SMS.")
        # Le parcours FOSA s'arrête ici depuis le 2026-07-26 (plus d'étape paiement
        # obligatoire) : voir paiements/views.py pour le contexte de cette décision.
        return redirect("commandes:detail", commande_id=commande.pk)
    except (services.StockInsuffisantError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("commandes:panier")


@formation_sanitaire_only_required
def historique(request):
    commandes = (
        Commande.objects.filter(formation_sanitaire=request.user.formation_sanitaire)
        .exclude(statut=StatutCommande.BROUILLON)
        .select_related("paiement")
        .order_by("-date_creation")
    )
    return render(request, "commandes/historique.html", {"commandes": commandes})


@formation_sanitaire_only_required
def detail(request, commande_id):
    commande = get_object_or_404(
        Commande.objects.select_related("paiement"),
        pk=commande_id,
        formation_sanitaire=request.user.formation_sanitaire,
    )
    return render(request, "commandes/detail.html", {"commande": commande})


@formation_sanitaire_only_required
def telecharger_pdf(request, commande_id):
    """Téléchargement du PDF par la FOSA elle-même (pour l'enregistrer ou le partager,
    par exemple via le bouton « Partager par WhatsApp »)."""
    commande = get_object_or_404(
        Commande, pk=commande_id, formation_sanitaire=request.user.formation_sanitaire
    )
    pdf_bytes = generer_pdf_commande(commande)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="commande_{commande.pk}.pdf"'
    return response


@personnel_frps_required
def telecharger_pdf_staff(request, commande_id):
    """Téléchargement du PDF par le personnel FRPS (depuis la page notifications),
    sans restriction à une formation sanitaire précise."""
    commande = get_object_or_404(Commande, pk=commande_id)
    pdf_bytes = generer_pdf_commande(commande)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="commande_{commande.pk}.pdf"'
    return response


def pdf_commande(request, commande_id, token):
    """Sert le PDF de la commande sans authentification : accès protégé par un jeton
    signé (voir notifications.pdf), nécessaire pour que Twilio puisse le télécharger."""
    if not verifier_token_pdf(commande_id, token):
        raise Http404
    commande = get_object_or_404(Commande, pk=commande_id)
    pdf_bytes = generer_pdf_commande(commande)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="commande_{commande.pk}.pdf"'
    return response
