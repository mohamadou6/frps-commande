from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook

from accounts.decorators import personnel_frps_required
from accounts.models import FormationSanitaire
from catalogue.models import Magasin, Produit
from commandes.models import Commande, LigneCommande, StatutCommande

COMMANDES_EFFECTIVES = [StatutCommande.CONFIRMEE, StatutCommande.PAYEE]


def _periode_depuis_requete(request):
    aujourd_hui = date.today()
    debut = request.GET.get("debut") or str(aujourd_hui - timedelta(days=30))
    fin = request.GET.get("fin") or str(aujourd_hui)
    return debut, fin


def _reponse_xlsx(nom_fichier, entetes, lignes):
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(entetes)
    for ligne in lignes:
        feuille.append(list(ligne))

    reponse = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    reponse["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
    classeur.save(reponse)
    return reponse


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

    if request.GET.get("export") == "xlsx" and produit_selectionne:
        lignes_export = [
            (l["commande__formation_sanitaire__nom"], l["quantite"], l["nb_commandes"]) for l in repartition_fosa
        ]
        return _reponse_xlsx(
            f"statistiques_produit_{produit_selectionne.pk}.xlsx",
            ["Formation sanitaire", "Quantité", "Commandes"],
            lignes_export,
        )

    return render(
        request,
        "statistiques/par_produit.html",
        {
            "produits": produits,
            "produits_json": [{"id": p.id, "nom": p.nom} for p in produits],
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

    if request.GET.get("export") == "xlsx" and fosa_selectionnee:
        lignes_export = [(l["produit__nom"], l["quantite"]) for l in repartition_produits]
        return _reponse_xlsx(
            f"statistiques_fosa_{fosa_selectionnee.pk}.xlsx",
            ["Produit", "Quantité"],
            lignes_export,
        )

    return render(
        request,
        "statistiques/par_fosa.html",
        {
            "formations": formations,
            "formations_json": [{"id": f.id, "nom": f.nom} for f in formations],
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

    if request.GET.get("export") == "xlsx" and district:
        lignes_export = [
            (l["formation_sanitaire__nom"], l["nb_commandes"], l["montant"]) for l in repartition_fosa
        ]
        return _reponse_xlsx(
            f"statistiques_district_{district}.xlsx",
            ["Formation sanitaire", "Commandes", "Montant (FCFA)"],
            lignes_export,
        )

    return render(
        request,
        "statistiques/par_district.html",
        {
            "districts": districts,
            "districts_json": [{"id": d, "nom": d} for d in districts],
            "debut": debut,
            "fin": fin,
            "district": district,
            "resultat": resultat,
            "repartition_fosa": repartition_fosa,
        },
    )


@personnel_frps_required
def stock(request):
    debut, fin = _periode_depuis_requete(request)

    produits_catalogue = Produit.objects.filter(magasin__in=[Magasin.PRINCIPAL, Magasin.UCPC])
    nb_produits_catalogue = produits_catalogue.count()
    nb_en_stock = produits_catalogue.filter(stock_disponible__gt=0).count()
    nb_rupture = produits_catalogue.filter(stock_disponible=0).count()
    quantite_totale_stock = produits_catalogue.aggregate(total=Sum("stock_disponible"))["total"] or 0
    valeur_totale_stock = produits_catalogue.aggregate(
        total=Sum(
            ExpressionWrapper(F("stock_disponible") * F("prix_unitaire"), output_field=DecimalField())
        )
    )["total"] or Decimal("0")

    ruptures_qs = (
        LigneCommande.objects.filter(
            produit__in=produits_catalogue.filter(stock_disponible=0),
            commande__statut__in=COMMANDES_EFFECTIVES,
            commande__date_confirmation__date__gte=debut,
            commande__date_confirmation__date__lte=fin,
        )
        .values("produit__nom")
        .annotate(quantite=Sum("quantite"), nb_commandes=Count("commande", distinct=True))
        .order_by("-quantite")
    )

    export = request.GET.get("export")
    if export == "rupture":
        lignes_export = [(l["produit__nom"], l["quantite"], l["nb_commandes"]) for l in ruptures_qs]
        return _reponse_xlsx(
            "stock_ruptures_les_plus_commandees.xlsx",
            ["Produit", "Quantité commandée", "Commandes"],
            lignes_export,
        )
    if export == "stock":
        lignes_export = [(p.nom, p.stock_disponible) for p in produits_catalogue.order_by("nom")]
        return _reponse_xlsx(
            "stock_produits.xlsx",
            ["Produit", "Stock disponible"],
            lignes_export,
        )

    return render(
        request,
        "statistiques/stock.html",
        {
            "debut": debut,
            "fin": fin,
            "nb_produits_catalogue": nb_produits_catalogue,
            "nb_en_stock": nb_en_stock,
            "nb_rupture": nb_rupture,
            "quantite_totale_stock": quantite_totale_stock,
            "valeur_totale_stock": valeur_totale_stock,
            "produits_stock": produits_catalogue.order_by("nom"),
            "ruptures_plus_commandes": ruptures_qs[:20],
        },
    )
