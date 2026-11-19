"""Pages de l'espace FOSA : alertes de retour en stock, produits habituels et
commande mensuelle programmée."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import formation_sanitaire_only_required

from . import espace_fosa, recherche, services
from .models import AlerteStock, CommandeMensuelle, Produit, ProduitHabituel


def _retour(request, defaut):
    """Revient à la page d'où vient le clic (catalogue filtré, promotions…), jamais
    vers une adresse extérieure."""
    suivant = request.POST.get("suivant", "")
    if suivant.startswith("/") and not suivant.startswith("//"):
        return redirect(suivant)
    return redirect(defaut)


def _quantites_panier(fosa):
    from commandes.models import Commande, StatutCommande

    panier = Commande.objects.filter(formation_sanitaire=fosa, statut=StatutCommande.BROUILLON).first()
    return dict(panier.lignes.values_list("produit_id", "quantite")) if panier else {}


def _signaler_mise_au_panier(request, ajoutes, reduits, indisponibles, origine):
    if ajoutes or reduits:
        messages.success(
            request, f"{len(ajoutes) + len(reduits)} produit(s) {origine} mis au panier. Vérifiez avant de valider."
        )
    if reduits:
        messages.warning(request, "Quantité réduite au stock disponible : " + ", ".join(reduits) + ".")
    if indisponibles:
        messages.warning(request, "Indisponible(s) pour le moment : " + ", ".join(indisponibles) + ".")


# ---------- Alertes de retour en stock ----------


@formation_sanitaire_only_required
def alertes(request):
    fosa = request.user.formation_sanitaire
    mes_alertes = list(AlerteStock.objects.filter(formation_sanitaire=fosa).select_related("produit", "produit__rayon"))
    en_attente = [a for a in mes_alertes if not a.produit.en_stock]
    revenus = [a.produit for a in mes_alertes if a.produit.en_stock]
    services.annoter_fiches(revenus, _quantites_panier(fosa), fosa)

    query = request.GET.get("q", "").strip()
    resultats = []
    if query:
        suivis = {a.produit_id for a in mes_alertes}
        resultats = recherche.filtrer(espace_fosa.produits_en_rupture().order_by("nom"), query)[:30]
        for produit in resultats:
            produit.alerte_demandee = produit.pk in suivis
    return render(
        request,
        "catalogue/alertes.html",
        {"en_attente": en_attente, "revenus": revenus, "query": query, "resultats": resultats},
    )


@formation_sanitaire_only_required
@require_POST
def demander_alerte(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id)
    try:
        espace_fosa.demander_alerte(request.user.formation_sanitaire, produit)
    except ValueError as exc:
        messages.info(request, str(exc))
    else:
        messages.success(request, f"C'est noté : vous serez prévenu dès que {produit.nom} sera de retour.")
    return _retour(request, "catalogue:alertes")


@formation_sanitaire_only_required
@require_POST
def annuler_alerte(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id)
    if espace_fosa.annuler_alerte(request.user.formation_sanitaire, produit):
        messages.success(request, f"Alerte retirée pour {produit.nom}.")
    return _retour(request, "catalogue:alertes")


# ---------- Produits habituels et commande mensuelle ----------


@formation_sanitaire_only_required
def habituels(request):
    fosa = request.user.formation_sanitaire
    if request.method == "POST":
        quantites = {}
        for cle, valeur in request.POST.items():
            if cle.startswith("quantite_"):
                try:
                    quantites[int(cle.removeprefix("quantite_"))] = max(0, int(valeur or 0))
                except ValueError:
                    continue
        espace_fosa.modifier_quantites_habituelles(fosa, quantites)
        if request.POST.get("action") == "panier":
            _signaler_mise_au_panier(request, *espace_fosa.mettre_habituels_au_panier(fosa), "habituels")
            return redirect("commandes:panier")
        messages.success(request, "Quantités enregistrées.")
        return redirect("catalogue:habituels")

    liste = list(ProduitHabituel.objects.filter(formation_sanitaire=fosa).select_related("produit", "produit__rayon"))
    services.annoter_fiches([h.produit for h in liste], _quantites_panier(fosa), fosa)
    return render(
        request,
        "catalogue/habituels.html",
        {
            "habituels": liste,
            "programme": CommandeMensuelle.objects.filter(formation_sanitaire=fosa).first(),
            "jours": range(1, 29),
            "a_proposer": not liste and bool(espace_fosa.produits_les_plus_commandes(fosa, limite=1)),
        },
    )


@formation_sanitaire_only_required
@require_POST
def basculer_habituel(request, produit_id):
    """L'étoile des fiches produit : ajoute ou retire le produit de la liste."""
    fosa = request.user.formation_sanitaire
    produit = get_object_or_404(Produit, pk=produit_id)
    if espace_fosa.retirer_habituel(fosa, produit):
        messages.info(request, f"{produit.nom} retiré de vos produits habituels.")
    else:
        espace_fosa.ajouter_habituel(fosa, produit, request.POST.get("quantite") or 1)
        messages.success(request, f"⭐ {produit.nom} ajouté à vos produits habituels.")
    return _retour(request, "catalogue:habituels")


@formation_sanitaire_only_required
@require_POST
def preremplir_habituels(request):
    ajoutes = espace_fosa.preremplir_habituels(request.user.formation_sanitaire)
    if ajoutes:
        messages.success(request, f"{ajoutes} produit(s) parmi vos plus commandés ajoutés à la liste.")
    else:
        messages.info(request, "Aucun nouveau produit à ajouter : passez d'abord quelques commandes.")
    return redirect("catalogue:habituels")


@formation_sanitaire_only_required
@require_POST
def programmer_commande(request):
    fosa = request.user.formation_sanitaire
    try:
        programme = espace_fosa.programmer_commande_mensuelle(
            fosa, request.POST.get("jour"), active=request.POST.get("active") == "1"
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        if programme.active:
            messages.success(
                request,
                f"Commande mensuelle activée : à partir du {programme.jour_du_mois} de chaque mois, votre panier "
                "sera préparé avec vos produits habituels. Vous n'aurez plus qu'à le valider.",
            )
        else:
            messages.info(request, "Commande mensuelle désactivée.")
    return redirect("catalogue:habituels")
