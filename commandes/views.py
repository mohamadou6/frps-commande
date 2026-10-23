import json
import uuid

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import (
    admin_frps_required,
    formation_sanitaire_only_required,
    personnel_frps_required,
)
from catalogue.models import Produit
from frps_project.formatage import formater_montant, formater_prix
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
    erreur = None
    try:
        quantite = int(request.POST.get("quantite", "1"))
    except ValueError:
        erreur = "Quantité invalide."
    else:
        try:
            services.ajouter_produit(commande, produit, quantite)
        except (services.StockInsuffisantError, ValueError) as exc:
            erreur = str(exc)

    # Le catalogue ajoute sans recharger la page (js/app.js) : sur réseau lent, recharger
    # tout le catalogue à chaque produit coûtait une dizaine de secondes. Sans
    # JavaScript, le formulaire arrive ici aussi et repart sur le catalogue.
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if erreur:
            return JsonResponse({"ok": False, "message": erreur}, status=400)
        return JsonResponse(
            {
                "ok": True,
                "message": f"{produit.nom} ajouté au panier.",
                "quantite": f"{quantite:,}".replace(",", " "),
                "panier_nb": commande.lignes.count(),
                "panier_montant": formater_montant(commande.montant_total),
                "panier_montant_nul": not commande.montant_total,
            }
        )

    if erreur:
        messages.error(request, erreur)
    else:
        messages.success(request, f"{produit.nom} ajouté au panier.")
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


# Bornes d'une demande hors connexion : larges (le catalogue compte ~1 200 produits),
# elles n'écartent qu'un envoi manifestement aberrant.
MAX_LIGNES_DEMANDE = 2000
MAX_QUANTITE_DEMANDEE = 10_000_000


def _lire_quantites(lignes):
    """[{"produit": id, "quantite": n}, …] -> {id: n}. Lève ValueError si illisible.

    Seuls le produit et la quantité sont lus : un prix envoyé par le téléphone est
    ignoré, le serveur le recalcule toujours."""
    if not isinstance(lignes, list) or not lignes or len(lignes) > MAX_LIGNES_DEMANDE:
        raise ValueError("lignes")
    quantites = {}
    for ligne in lignes:
        produit_id = int(ligne["produit"])
        quantite = int(ligne["quantite"])
        if quantite <= 0 or quantite > MAX_QUANTITE_DEMANDEE:
            raise ValueError("quantite")
        quantites[produit_id] = quantites.get(produit_id, 0) + quantite
    return quantites


def _resultat_demande(commande, deja_recue):
    lignes = commande.lignes.select_related("produit").order_by("produit__nom")
    return {
        "ok": True,
        "uuid": str(commande.uuid_client),
        "commande_id": commande.pk,
        "statut": commande.statut,
        "statut_libelle": commande.get_statut_display(),
        "montant_total": formater_montant(commande.montant_total),
        "url_detail": reverse("commandes:detail", args=[commande.pk]),
        "deja_recue": deja_recue,
        "lignes": [
            {
                "produit": ligne.produit_id,
                "nom": ligne.produit.nom,
                "demandee": ligne.quantite_demandee,
                "servie": ligne.quantite,
                "prix_unitaire": formater_prix(ligne.prix_unitaire_snapshot),
            }
            for ligne in lignes
        ],
    }


@formation_sanitaire_only_required
@require_POST
def synchroniser_demande(request):
    """Reçoit une commande préparée hors connexion (js/demandes.js) et la valide.

    Toujours du JSON, et un code qui dit au téléphone quoi faire de sa demande :
    200 = traitée (la garder comme résultat), 400 = refusée pour de bon (ne plus la
    renvoyer), 409 = pas pour ce compte (la garder pour le bon compte), 503 = à
    renvoyer plus tard. Une redirection vers la connexion (session expirée) n'est pas
    du JSON : le téléphone garde aussi la demande.
    """
    try:
        donnees = json.loads(request.body)
        uuid_client = uuid.UUID(str(donnees["uuid"]))
        quantites = _lire_quantites(donnees["lignes"])
        # Panier en ligne confirmé sans réseau (voir services.recevoir_demande).
        panier_id = int(donnees["panier"]) if donnees.get("panier") is not None else None
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False, "code": "illisible", "message": "Demande illisible."}, status=400)

    # Le téléphone peut servir à plusieurs comptes : une demande préparée sous un
    # compte ne doit jamais partir sous la session d'un autre.
    compte = donnees.get("compte")
    if compte is not None and str(compte) != str(request.user.pk):
        return JsonResponse(
            {"ok": False, "code": "autre_compte", "message": "Demande préparée sous un autre compte."}, status=409
        )

    try:
        commande, recue_maintenant = services.synchroniser_demande(
            request.user.formation_sanitaire, uuid_client, quantites, panier_id
        )
    except services.DemandeInvalideError as exc:
        return JsonResponse({"ok": False, "code": "refusee", "message": str(exc)}, status=400)
    except services.StockInsuffisantError:
        # Course avec une autre commande malgré le verrou (base sans SELECT … FOR
        # UPDATE) : rien n'a été débité, la demande reste en attente et repartira.
        return JsonResponse({"ok": False, "code": "reessayer", "message": "Réessayer."}, status=503)
    return JsonResponse(_resultat_demande(commande, deja_recue=not recue_maintenant))


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
