"""Prix de vente du moment : promotions décidées par l'admin, et information des FOSA
sur les baisses du prix de vente.

Deux choses distinctes, à ne pas confondre :
- une **promotion** est posée par l'admin pour une période ; pendant cette période, la
  FOSA paie le prix promotionnel (prix_de_vente) ;
- une **baisse de prix** est un changement durable du prix de vente (import Excel,
  admin), détecté automatiquement et seulement signalé aux FOSA (menu Baisses de prix).
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    PROMOTION_DUREE_JOURS,
    PROMOTION_SEUIL_POURCENT,
    BaissePrix,
    Magasin,
    Produit,
    Promotion,
)

MAGASINS_CATALOGUE = [Magasin.PRINCIPAL, Magasin.UCPC]
# Durée pendant laquelle une baisse de prix reste signalée aux FOSA.
BAISSE_DUREE_JOURS = PROMOTION_DUREE_JOURS


# ---------- Promotions (posées par l'admin) ----------


def _promotions_du_jour():
    """Promotions actives aujourd'hui dont le prix est encore sous le prix normal (si
    l'admin a baissé le prix normal en dessous entre-temps, la promotion n'a plus
    d'objet et le prix normal s'applique)."""
    aujourdhui = timezone.localdate()
    return Promotion.objects.filter(
        active=True,
        date_debut__lte=aujourdhui,
        date_fin__gte=aujourdhui,
        prix_promotionnel__lt=F("produit__prix_unitaire"),
    )


def promotions_en_cours():
    """Promotions visibles des FOSA : en cours et sur un produit commandable."""
    return (
        _promotions_du_jour()
        .filter(produit__actif=True, produit__stock_disponible__gt=0, produit__magasin__in=MAGASINS_CATALOGUE)
        .select_related("produit", "produit__rayon")
        .order_by("date_fin", "produit__nom")
    )


def prix_promotionnels(produit_ids=None):
    """{produit_id: prix promotionnel} des promotions du jour. Une seule requête pour
    toute une liste de produits (catalogue, commande hors connexion)."""
    promos = _promotions_du_jour()
    if produit_ids is not None:
        promos = promos.filter(produit_id__in=list(produit_ids))
    resultat = {}
    for produit_id, prix in promos.values_list("produit_id", "prix_promotionnel"):
        resultat[produit_id] = min(prix, resultat.get(produit_id, prix))
    return resultat


def prix_de_vente(produit, promos=None):
    """Prix que la FOSA paie aujourd'hui : le prix promotionnel s'il y en a un, sinon
    le prix normal. `promos` : résultat de prix_promotionnels(), pour éviter une
    requête par produit dans une boucle."""
    if promos is None:
        promos = prix_promotionnels([produit.pk])
    return promos.get(produit.pk, produit.prix_unitaire)


def creer_promotion(produit, prix_promotionnel, date_debut, date_fin, message="", auteur=None):
    try:
        prix = Decimal(str(prix_promotionnel).replace(" ", "").replace(",", "."))
    except Exception:  # noqa: BLE001 - toute saisie illisible donne le même message
        raise ValueError("Prix promotionnel illisible.")
    if prix <= 0:
        raise ValueError("Le prix promotionnel doit être supérieur à 0.")
    if prix >= produit.prix_unitaire:
        raise ValueError(
            f"Le prix promotionnel doit être inférieur au prix normal ({produit.prix_unitaire} FCFA)."
        )
    if not date_debut or not date_fin:
        raise ValueError("Indiquez la date de début et la date de fin.")
    if date_fin < date_debut:
        raise ValueError("La date de fin doit suivre la date de début.")
    if date_fin < timezone.localdate():
        raise ValueError("Cette période est déjà passée.")

    with transaction.atomic():
        # Verrou sur le produit : deux saisies simultanées ne doivent pas créer deux
        # promotions qui se chevauchent.
        Produit.objects.select_for_update().filter(pk=produit.pk).first()
        chevauchement = Promotion.objects.filter(
            produit=produit, active=True, date_debut__lte=date_fin, date_fin__gte=date_debut
        ).first()
        if chevauchement:
            raise ValueError(
                f"{produit.nom} a déjà une promotion du {chevauchement.date_debut:%d/%m/%Y} "
                f"au {chevauchement.date_fin:%d/%m/%Y}. Arrêtez-la d'abord."
            )
        return Promotion.objects.create(
            produit=produit,
            prix_promotionnel=prix.quantize(Decimal("0.01")),
            date_debut=date_debut,
            date_fin=date_fin,
            message=(message or "").strip()[:150],
            creee_par=auteur,
        )


def arreter_promotion(promotion):
    promotion.active = False
    promotion.save(update_fields=["active"])
    return promotion


# ---------- Baisses du prix de vente (information) ----------


def noter_baisses_prix(changements):
    """Enregistre les baisses de prix parmi `changements` : [(produit, ancien_prix, nouveau_prix)].

    À appeler partout où le prix de vente change (import Excel, admin, update_stock) :
    `bulk_update` ne passe ni par save() ni par les signaux, d'où cet appel explicite.
    Retourne le nombre de baisses enregistrées."""
    seuil = Decimal(1) - Decimal(PROMOTION_SEUIL_POURCENT) / 100
    baisses = [
        BaissePrix(produit=produit, ancien_prix=ancien, nouveau_prix=nouveau)
        for produit, ancien, nouveau in changements
        if ancien and nouveau is not None and Decimal(ancien) > 0 and Decimal(nouveau) <= Decimal(ancien) * seuil
    ]
    BaissePrix.objects.bulk_create(baisses)
    return len(baisses)


def baisses_prix_recentes():
    """Produits dont le prix de vente a baissé récemment : une entrée par produit, la
    plus récente d'abord.

    Signalé = baisse des BAISSE_DUREE_JOURS derniers jours, non masquée par l'admin,
    prix pas remonté depuis, produit commandable. Si le prix a baissé plusieurs fois,
    « avant » est le prix le plus haut de la période : la baisse totale constatée."""
    debut = timezone.now() - timedelta(days=BAISSE_DUREE_JOURS)
    baisses = (
        BaissePrix.objects.filter(
            date__gte=debut,
            visible=True,
            produit__actif=True,
            produit__stock_disponible__gt=0,
            produit__magasin__in=MAGASINS_CATALOGUE,
        )
        .select_related("produit", "produit__rayon")
        .order_by("-date")
    )

    par_produit = {}
    for baisse in baisses:
        produit = baisse.produit
        if produit.pk not in par_produit:
            if produit.prix_unitaire > baisse.nouveau_prix:  # prix remonté depuis
                par_produit[produit.pk] = None
                continue
            produit.prix_avant = baisse.ancien_prix
            produit.date_baisse = baisse.date
            par_produit[produit.pk] = produit
        elif par_produit[produit.pk] is not None:
            par_produit[produit.pk].prix_avant = max(par_produit[produit.pk].prix_avant, baisse.ancien_prix)

    resultat = [p for p in par_produit.values() if p is not None]
    for produit in resultat:
        produit.pourcentage_baisse = round((1 - produit.prix_unitaire / produit.prix_avant) * 100)
    return resultat


def masquer_baisse(produit):
    """Retire un produit du menu Baisses de prix (toutes ses baisses de la période)."""
    debut = timezone.now() - timedelta(days=BAISSE_DUREE_JOURS)
    return BaissePrix.objects.filter(produit=produit, date__gte=debut, visible=True).update(visible=False)


def toutes_les_promotions():
    """Les deux types de promotion présentés aux FOSA dans le menu Promotions :
    (offres spéciales posées par l'admin, produits dont le prix a baissé).

    Un produit en offre spéciale n'est pas répété dans les baisses de prix : c'est le
    prix promotionnel qu'il paie, pas le nouveau prix normal."""
    offres = list(promotions_en_cours())
    en_offre = {promo.produit_id for promo in offres}
    baisses = [p for p in baisses_prix_recentes() if p.pk not in en_offre]
    return offres, baisses


def nombre_promotions():
    """Total des deux types, pour la pastille du menu et le bandeau du catalogue."""
    offres, baisses = toutes_les_promotions()
    return len(offres) + len(baisses)

