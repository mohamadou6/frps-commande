from datetime import date, timedelta

from django.db.models import Count, Sum
from django.shortcuts import render

from accounts.decorators import personnel_frps_required
from accounts.models import FormationSanitaire
from catalogue.models import Produit
from commandes.models import Commande, LigneCommande, StatutCommande

COMMANDES_EFFECTIVES = [StatutCommande.CONFIRMEE, StatutCommande.PAYEE]


def _periode_depuis_requete(request):
    aujourd_hui = date.today()
    debut = request.GET.get("debut") or str(aujourd_hui - timedelta(days=30))
    fin = request.GET.get("fin") or str(aujourd_hui)
    return debut, fin


@personnel_frps_required
def index(request):
    return render(request, "statistiques/index.html")


@personnel_frps_required
def par_produit(request):
    produits = Produit.objects.order_by("nom")
    debut, fin = _periode_depuis_requete(request)
    produit_id = request.GET.get("produit")

    produit_selectionne = None
    resultat = None
    repartition_fosa = []

    if produit_id:
        produit_selectionne = produits.filter(pk=produit_id).first()
        if produit_selectionne:
            lignes = LigneCommande.objects.filter(
                produit=produit_selectionne,
                commande__statut__in=COMMANDES_EFFECTIVES,
                commande__date_confirmation__date__gte=debut,
                commande__date_confirmation__date__lte=fin,
            )
            resultat = lignes.aggregate(
                quantite_totale=Sum("quantite"),
                nb_commandes=Count("commande", distinct=True),
                nb_fosa=Count("commande__formation_sanitaire", distinct=True),
            )
            repartition_fosa = (
                lignes.values("commande__formation_sanitaire__nom")
                .annotate(quantite=Sum("quantite"), nb_commandes=Count("commande", distinct=True))
                .order_by("-quantite")
            )

    return render(
        request,
        "statistiques/par_produit.html",
        {
            "produits": produits,
            "debut": debut,
            "fin": fin,
            "produit_id": produit_id,
            "produit_selectionne": produit_selectionne,
            "resultat": resultat,
            "repartition_fosa": repartition_fosa,
        },
    )


@personnel_frps_required
def par_fosa(request):
    formations = FormationSanitaire.objects.order_by("nom")
    debut, fin = _periode_depuis_requete(request)
    fosa_id = request.GET.get("fosa")

    fosa_selectionnee = None
    resultat = None
    repartition_produits = []

    if fosa_id:
        fosa_selectionnee = formations.filter(pk=fosa_id).first()
        if fosa_selectionnee:
            commandes = Commande.objects.filter(
                formation_sanitaire=fosa_selectionnee,
                statut__in=COMMANDES_EFFECTIVES,
                date_confirmation__date__gte=debut,
                date_confirmation__date__lte=fin,
            )
            resultat = commandes.aggregate(nb_commandes=Count("id"), montant_total=Sum("montant_total"))
            resultat["nb_produits"] = (
                LigneCommande.objects.filter(commande__in=commandes).aggregate(total=Sum("quantite"))["total"] or 0
            )
            repartition_produits = (
                LigneCommande.objects.filter(commande__in=commandes)
                .values("produit__nom")
                .annotate(quantite=Sum("quantite"))
                .order_by("-quantite")
            )

    return render(
        request,
        "statistiques/par_fosa.html",
        {
            "formations": formations,
            "debut": debut,
            "fin": fin,
            "fosa_id": fosa_id,
            "fosa_selectionnee": fosa_selectionnee,
            "resultat": resultat,
            "repartition_produits": repartition_produits,
        },
    )


@personnel_frps_required
def par_district(request):
    districts = (
        FormationSanitaire.objects.exclude(district="")
        .values_list("district", flat=True)
        .distinct()
        .order_by("district")
    )
    debut, fin = _periode_depuis_requete(request)
    district = request.GET.get("district")

    resultat = None
    repartition_fosa = []

    if district:
        commandes = Commande.objects.filter(
            formation_sanitaire__district=district,
            statut__in=COMMANDES_EFFECTIVES,
            date_confirmation__date__gte=debut,
            date_confirmation__date__lte=fin,
        )
        resultat = commandes.aggregate(nb_commandes=Count("id"), montant_total=Sum("montant_total"))
        resultat["nb_produits"] = (
            LigneCommande.objects.filter(commande__in=commandes).aggregate(total=Sum("quantite"))["total"] or 0
        )
        repartition_fosa = (
            commandes.values("formation_sanitaire_id", "formation_sanitaire__nom")
            .annotate(nb_commandes=Count("id", distinct=True), montant=Sum("montant_total"))
            .order_by("formation_sanitaire__nom")
        )
        resultat["nb_fosa"] = len(repartition_fosa)

    return render(
        request,
        "statistiques/par_district.html",
        {
            "districts": districts,
            "debut": debut,
            "fin": fin,
            "district": district,
            "resultat": resultat,
            "repartition_fosa": repartition_fosa,
        },
    )
