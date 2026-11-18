import unicodedata
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from openpyxl import load_workbook

from accounts.decorators import admin_frps_required, formation_sanitaire_required
from commandes.models import Commande, StatutCommande

from .models import Magasin, Produit, Promotion, Rayon
from . import services
from .services import noter_baisses_prix

SLUG_AUTRES = "autres"


@formation_sanitaire_required
def liste(request):
    query = request.GET.get("q", "").strip()
    rayon_slug = request.GET.get("rayon", "").strip()

    produits_visibles = Produit.objects.filter(
        actif=True, magasin__in=[Magasin.PRINCIPAL, Magasin.UCPC], stock_disponible__gt=0
    )

    rayons = list(
        Rayon.objects.filter(produits__in=produits_visibles)
        .distinct()
        .annotate(nb_produits=models.Count("produits", filter=models.Q(produits__in=produits_visibles)))
        .order_by("nom")
    )

    # Rayon virtuel « Autres » : les produits sans rayon affecté, sinon introuvables
    # autrement que par la recherche.
    nb_sans_rayon = produits_visibles.filter(rayon__isnull=True).count()
    if nb_sans_rayon:
        rayons.append(Rayon(slug=SLUG_AUTRES, nom="Autres", icone="📦"))
        rayons[-1].nb_produits = nb_sans_rayon

    produits = produits_visibles.order_by("nom")
    if rayon_slug == SLUG_AUTRES:
        produits = produits.filter(rayon__isnull=True)
    elif rayon_slug:
        produits = produits.filter(rayon__slug=rayon_slug)
    if query:
        produits = produits.filter(nom__icontains=query)

    rayon_actif = next((r for r in rayons if r.slug == rayon_slug), None)

    # Quantités déjà au panier, pour les signaler sur les cartes : sans ce repère,
    # sur une centaine de produits, la même ligne était facilement ajoutée deux fois.
    # On lit le brouillon existant sans passer par get_panier(), qui en créerait un
    # à chaque visite du catalogue. L'admin FRPS peut consulter le catalogue mais
    # n'a pas de formation sanitaire, donc pas de panier.
    quantites_panier = {}
    if request.user.is_formation_sanitaire:
        panier = Commande.objects.filter(
            formation_sanitaire=request.user.formation_sanitaire, statut=StatutCommande.BROUILLON
        ).first()
        if panier:
            quantites_panier = dict(panier.lignes.values_list("produit_id", "quantite"))

    produits = list(produits)
    _annoter_offres(produits, quantites_panier)

    return render(
        request,
        "catalogue/liste.html",
        {
            "produits": produits,
            "query": query,
            "rayons": rayons,
            "rayon_actif": rayon_actif,
            "nb_produits_total": produits_visibles.count(),
            "nb_promotions": services.nombre_promotions(),
        },
    )


def _quantites_panier(request):
    """Quantités déjà au panier de la FOSA ({produit_id: quantité}). L'admin FRPS n'a
    pas de formation sanitaire, donc pas de panier."""
    if not request.user.is_formation_sanitaire:
        return {}
    panier = Commande.objects.filter(
        formation_sanitaire=request.user.formation_sanitaire, statut=StatutCommande.BROUILLON
    ).first()
    return dict(panier.lignes.values_list("produit_id", "quantite")) if panier else {}


def _annoter_offres(produits, quantites_panier):
    """Pose sur chaque fiche : quantité au panier, prix du jour (promotion comprise)
    et pourcentage de la promotion ou de la baisse récente, pour les étiquettes."""
    promos = services.prix_promotionnels([p.pk for p in produits])
    baisses = {p.pk: p.pourcentage_baisse for p in services.baisses_prix_recentes()}
    for produit in produits:
        produit.quantite_panier = quantites_panier.get(produit.pk, 0)
        produit.prix_du_jour = services.prix_de_vente(produit, promos)
        produit.en_promotion = produit.pk in promos
        produit.pourcentage_promotion = (
            round((1 - produit.prix_du_jour / produit.prix_unitaire) * 100) if produit.en_promotion else None
        )
        produit.pourcentage_baisse = baisses.get(produit.pk)


@formation_sanitaire_required
def promotions(request):
    """Menu Promotions des FOSA, deux types :
    - offres spéciales : créées par l'admin (prix promotionnel, durée limitée) ;
    - prix en baisse : le prix de vente a baissé (détecté à l'import ou dans l'admin).
    `?type=offre` ou `?type=baisse` n'affiche qu'un type."""
    offres, baisses = services.toutes_les_promotions()
    produits_offres = [promo.produit for promo in offres]
    for promo, produit in zip(offres, produits_offres):
        produit.promotion = promo
    quantites = _quantites_panier(request)
    _annoter_offres(produits_offres, quantites)
    _annoter_offres(baisses, quantites)

    type_affiche = request.GET.get("type", "")
    if type_affiche not in ("offre", "baisse"):
        type_affiche = ""
    return render(
        request,
        "catalogue/promotions.html",
        {
            "offres": produits_offres if type_affiche != "baisse" else [],
            "baisses": baisses if type_affiche != "offre" else [],
            "nb_offres": len(produits_offres),
            "nb_baisses": len(baisses),
            "type_affiche": type_affiche,
            "duree_baisse": services.BAISSE_DUREE_JOURS,
        },
    )


@admin_frps_required
@require_POST
def masquer_baisse(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id)
    if services.masquer_baisse(produit):
        messages.success(request, f"{produit.nom} retiré des promotions (prix en baisse).")
    return redirect(f"{reverse('catalogue:promotions')}?type=baisse")


@admin_frps_required
def gerer_promotions(request):
    """Mettre un produit en promotion (prix promotionnel + période) et suivre les
    promotions en cours, à venir et passées."""
    saisie = {cle: request.POST.get(cle, "") for cle in ("produit", "prix", "debut", "fin", "message")}
    if request.method == "POST":
        produit = Produit.objects.filter(pk=saisie["produit"] or 0).first()
        if produit is None:
            messages.error(request, "Choisissez un produit dans la liste.")
        else:
            try:
                promotion = services.creer_promotion(
                    produit,
                    saisie["prix"],
                    parse_date(saisie["debut"] or ""),
                    parse_date(saisie["fin"] or ""),
                    saisie["message"],
                    auteur=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"{produit.nom} en promotion à {promotion.prix_promotionnel} FCFA "
                    f"du {promotion.date_debut:%d/%m/%Y} au {promotion.date_fin:%d/%m/%Y}.",
                )
                return redirect("catalogue:gerer_promotions")

    aujourdhui = timezone.localdate()
    toutes = Promotion.objects.select_related("produit").order_by("-date_debut")
    return render(
        request,
        "catalogue/gerer_promotions.html",
        {
            "en_cours": toutes.filter(active=True, date_debut__lte=aujourdhui, date_fin__gte=aujourdhui),
            "a_venir": toutes.filter(active=True, date_debut__gt=aujourdhui),
            "terminees": (toutes.filter(active=False) | toutes.filter(date_fin__lt=aujourdhui))[:20],
            # Pour la recherche de produit (statistiques/js/combobox.js) : le prix normal
            # est dans le libellé, l'admin voit tout de suite de quoi il part.
            "produits_json": [
                {"id": p.pk, "nom": f"{p.nom} — {p.prix_unitaire} FCFA ({p.code_sage})"}
                for p in Produit.objects.filter(
                    actif=True, magasin__in=services.MAGASINS_CATALOGUE, prix_unitaire__gt=0
                ).order_by("nom")
            ],
            "produit_choisi": Produit.objects.filter(pk=saisie["produit"] or 0).first(),
            "saisie": saisie,
            "aujourdhui": aujourdhui,
        },
    )


@admin_frps_required
@require_POST
def arreter_promotion(request, promotion_id):
    promotion = get_object_or_404(Promotion, pk=promotion_id)
    services.arreter_promotion(promotion)
    messages.success(request, f"Promotion sur {promotion.produit.nom} arrêtée : le prix normal s'applique.")
    return redirect("catalogue:gerer_promotions")


def _normaliser_entete(valeur):
    if valeur is None:
        return ""
    texte = unicodedata.normalize("NFD", str(valeur).strip().lower())
    return "".join(c for c in texte if not unicodedata.combining(c))


def _decimal(valeur):
    if valeur is None or valeur == "":
        return Decimal("0.00")
    try:
        return Decimal(str(valeur).strip()).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _lire_fichier_produits(fichier):
    """Lit un classeur Excel dont l'en-tête contient une colonne code produit
    (ex. code_sage), une colonne prix (ex. prix_unitaire) et une colonne stock
    (ex. stock_disponible), dans n'importe quel ordre. La colonne nom est lue
    si présente. Retourne un dict {code_sage: {"nom": str|None, "prix": Decimal,
    "stock": int}}. Lève ValueError si l'en-tête attendu est introuvable."""
    classeur = load_workbook(filename=fichier, data_only=True, read_only=True)
    feuille = classeur.active
    lignes = feuille.iter_rows(values_only=True)

    entetes = next(lignes, None)
    if entetes is None:
        raise ValueError("Le fichier est vide.")

    colonnes = {}
    for index, entete in enumerate(entetes):
        cle = _normaliser_entete(entete)
        if "code" in cle and "code_sage" not in colonnes:
            colonnes["code_sage"] = index
        elif "nom" in cle and "nom" not in colonnes:
            colonnes["nom"] = index
        elif "prix" in cle and "prix_unitaire" not in colonnes:
            colonnes["prix_unitaire"] = index
        elif "stock" in cle and "stock_disponible" not in colonnes:
            colonnes["stock_disponible"] = index

    manquantes = [c for c in ("code_sage", "prix_unitaire", "stock_disponible") if c not in colonnes]
    if manquantes:
        raise ValueError(
            "Colonnes introuvables dans l'en-tête du fichier : "
            + ", ".join(manquantes)
            + ". Le fichier doit avoir une colonne code produit (ex. code_sage), "
            "une colonne prix (ex. prix_unitaire) et une colonne stock "
            "(ex. stock_disponible)."
        )

    updates = {}
    for ligne in lignes:
        if ligne is None or all(valeur is None for valeur in ligne):
            continue
        code_sage = ligne[colonnes["code_sage"]]
        if code_sage is None or not str(code_sage).strip():
            continue
        code_sage = str(code_sage).strip()
        nom = None
        if "nom" in colonnes:
            val_nom = ligne[colonnes["nom"]] if colonnes["nom"] < len(ligne) else None
            if val_nom is not None:
                nom = str(val_nom).strip() or None
        prix = _decimal(ligne[colonnes["prix_unitaire"]])
        stock = int(_decimal(ligne[colonnes["stock_disponible"]]))
        updates[code_sage] = {"nom": nom, "prix": prix, "stock": stock}
    return updates


@admin_frps_required
def importer_produits(request):
    resultats = None

    if request.method == "POST":
        fichier = request.FILES.get("fichier")
        if not fichier:
            messages.error(request, "Aucun fichier sélectionné.")
        elif not fichier.name.lower().endswith((".xlsx", ".xlsm")):
            messages.error(request, "Le fichier doit être un classeur Excel (.xlsx).")
        else:
            try:
                updates = _lire_fichier_produits(fichier)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                produits = {p.code_sage: p for p in Produit.objects.filter(code_sage__in=updates.keys())}

                modifies = []
                crees = []
                nb_inchanges = 0
                a_sauvegarder = []
                a_creer = []
                baisses = []

                for code_sage, donnees in updates.items():
                    prix = donnees["prix"]
                    stock = donnees["stock"]
                    nom = donnees["nom"] or code_sage
                    produit = produits.get(code_sage)
                    if produit is None:
                        a_creer.append(Produit(
                            code_sage=code_sage,
                            nom=nom,
                            prix_unitaire=prix,
                            stock_disponible=stock,
                        ))
                        crees.append({"code_sage": code_sage, "nom": nom, "prix": prix, "stock": stock})
                        continue
                    if produit.prix_unitaire == prix and produit.stock_disponible == stock:
                        nb_inchanges += 1
                        continue
                    if prix > produit.prix_unitaire:
                        variation_prix = "hausse"
                    elif prix < produit.prix_unitaire:
                        variation_prix = "baisse"
                    else:
                        variation_prix = ""
                    modifies.append(
                        {
                            "code_sage": code_sage,
                            "nom": produit.nom,
                            "ancien_prix": produit.prix_unitaire,
                            "nouveau_prix": prix,
                            "variation_prix": variation_prix,
                            "ancien_stock": produit.stock_disponible,
                            "nouveau_stock": stock,
                        }
                    )
                    if variation_prix == "baisse":
                        baisses.append((produit, produit.prix_unitaire, prix))
                    produit.prix_unitaire = prix
                    produit.stock_disponible = stock
                    a_sauvegarder.append(produit)

                if a_sauvegarder:
                    with transaction.atomic():
                        Produit.objects.bulk_update(
                            a_sauvegarder, ["prix_unitaire", "stock_disponible"], batch_size=200
                        )
                        nb_promotions = noter_baisses_prix(baisses)
                    if nb_promotions:
                        messages.info(
                            request,
                            f"{nb_promotions} baisse(s) de prix ajoutée(s) aux Promotions des FOSA (type « prix en baisse »).",
                        )
                if a_creer:
                    Produit.objects.bulk_create(a_creer, batch_size=200)

                # Changements de prix en tête de liste : noyés parmi les simples
                # mouvements de stock, ils passaient inaperçus.
                modifies.sort(key=lambda m: m["variation_prix"] == "")

                resultats = {
                    "total_lignes": len(updates),
                    "modifies": modifies,
                    "nb_modifies": len(modifies),
                    "nb_hausses": sum(m["variation_prix"] == "hausse" for m in modifies),
                    "nb_baisses": sum(m["variation_prix"] == "baisse" for m in modifies),
                    "nb_inchanges": nb_inchanges,
                    "crees": crees,
                    "nb_crees": len(crees),
                }

                msgs = []
                if modifies:
                    msgs.append(f"{len(modifies)} produit(s) mis à jour")
                if crees:
                    msgs.append(f"{len(crees)} nouveau(x) produit(s) créé(s)")
                if msgs:
                    messages.success(request, " · ".join(msgs) + ".")
                else:
                    messages.info(request, "Aucun changement détecté dans ce fichier.")

    return render(request, "catalogue/importer.html", {"resultats": resultats})
