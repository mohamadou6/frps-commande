from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import (
    admin_frps_required,
    formation_sanitaire_only_required,
    personnel_frps_required,
)
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
def modifier_quantite(request, produit_id):
    """Corrige la quantité d'une ligne directement depuis le panier : il fallait
    jusqu'ici retirer la ligne puis la rajouter depuis le catalogue."""
    produit = get_object_or_404(Produit, pk=produit_id)
    commande = services.get_panier(request.user.formation_sanitaire)

    try:
        quantite = int(request.POST.get("quantite", ""))
    except ValueError:
        messages.error(request, "Quantité invalide.")
        return redirect("commandes:panier")

    # Descendre à zéro équivaut à retirer la ligne, plutôt que de renvoyer une
    # erreur « la quantité doit être positive » que la FOSA ne saurait pas corriger.
    if quantite <= 0:
        services.retirer_produit(commande, produit)
        messages.success(request, f"{produit.nom} retiré du panier.")
        return redirect("commandes:panier")

    try:
        # ajouter_produit remplace la quantité de la ligne existante (il ne
        # l'incrémente pas) : c'est exactement l'opération voulue ici.
        services.ajouter_produit(commande, produit, quantite)
        messages.success(request, f"Quantité mise à jour : {produit.nom} × {quantite}.")
    except (services.StockInsuffisantError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("commandes:panier")


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


@admin_frps_required
@require_POST
def supprimer(request, commande_id):
    """Suppression d'une commande par l'admin FRPS, avec remise en stock.

    Cas d'usage : une FOSA a validé une commande par erreur. Réservé à l'admin
    (`admin_frps_required`) et en POST uniquement, pour qu'un simple lien visité — ou
    préchargé par un navigateur — ne puisse pas détruire une commande.
    """
    commande = get_object_or_404(Commande, pk=commande_id)
    libelle = f"#{commande.pk} de {commande.formation_sanitaire.nom}"
    services.supprimer_commande(commande)
    messages.success(request, f"Commande {libelle} supprimée. Le stock a été remis.")
    return redirect(request.POST.get("suivant") or "statistiques:index")
