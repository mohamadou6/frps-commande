"""Espace de la FOSA : alertes de retour en stock, produits habituels, suggestions
et commande mensuelle programmée."""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import AlerteStock, CommandeMensuelle, Magasin, Produit, ProduitHabituel

logger = logging.getLogger(__name__)

MAGASINS_CATALOGUE = [Magasin.PRINCIPAL, Magasin.UCPC]


def produits_commandables():
    return Produit.objects.filter(actif=True, stock_disponible__gt=0, magasin__in=MAGASINS_CATALOGUE)


def produits_en_rupture():
    """Produits du catalogue momentanément indisponibles : ceux qu'une FOSA peut suivre."""
    return Produit.objects.filter(actif=True, stock_disponible=0, magasin__in=MAGASINS_CATALOGUE)


# ---------- Alertes de retour en stock ----------


def demander_alerte(formation_sanitaire, produit):
    if produit.en_stock:
        raise ValueError(f"{produit.nom} est disponible : vous pouvez le commander dès maintenant.")
    alerte, cree = AlerteStock.objects.get_or_create(formation_sanitaire=formation_sanitaire, produit=produit)
    if not cree and alerte.date_notification is not None:
        # Déjà prévenue d'un précédent retour : on la réarme pour le prochain.
        alerte.date_notification = None
        alerte.date_demande = timezone.now()
        alerte.save(update_fields=["date_notification", "date_demande"])
    return alerte


def annuler_alerte(formation_sanitaire, produit):
    return AlerteStock.objects.filter(formation_sanitaire=formation_sanitaire, produit=produit).delete()[0]


def traiter_retours_en_stock():
    """Prévient les FOSA dont un produit attendu est revenu en stock : un seul push et
    un seul SMS par FOSA, quel que soit le nombre de produits revenus.

    À appeler après toute remise en stock (import Excel, admin, update_stock). Les
    alertes sont marquées prévenues dans la transaction, les envois partent après :
    un double appel ne prévient pas deux fois."""
    with transaction.atomic():
        alertes = list(
            AlerteStock.objects.select_for_update(of=("self",))
            .filter(
                date_notification__isnull=True,
                produit__actif=True,
                produit__stock_disponible__gt=0,
                produit__magasin__in=MAGASINS_CATALOGUE,
            )
            .select_related("produit", "formation_sanitaire__user")
        )
        if not alertes:
            return 0
        AlerteStock.objects.filter(pk__in=[a.pk for a in alertes]).update(date_notification=timezone.now())

    par_fosa = {}
    for alerte in alertes:
        par_fosa.setdefault(alerte.formation_sanitaire, []).append(alerte.produit)
    for fosa, produits in par_fosa.items():
        try:
            _prevenir_retour(fosa, produits)
        except Exception:  # noqa: BLE001 - un envoi raté ne doit pas bloquer les autres FOSA
            logger.exception("Retour en stock : %s non prévenue", fosa.nom)
    return len(alertes)


def _prevenir_retour(fosa, produits):
    from notifications.models import TypeEvenement
    from notifications.push import envoyer_push_a_fosa
    from notifications.services import _envoyer_a_destinataires, _sans_accents, numero_international

    noms = [p.nom for p in produits]
    titre = "De retour en stock" if len(noms) == 1 else f"{len(noms)} produits de retour en stock"
    envoyer_push_a_fosa(fosa, titre, ", ".join(noms)[:150], url="/catalogue/alertes/")

    numero = fosa.telephone_contact or fosa.user.telephone
    if not numero:
        return
    # Un seul segment SMS (voir notifications/services.py) : on résume si besoin.
    debut, fin = "FRPS-NO : de retour en stock : ", ". Commandez dans l'appli."
    inclus = []
    for rang, nom in enumerate(noms):
        reste = len(noms) - rang - 1
        candidat = _sans_accents(debut + ", ".join(inclus + [nom]) + (f" +{reste} autre(s)" if reste else "") + fin)
        if len(candidat) > 155:
            break
        inclus.append(nom)
    reste = len(noms) - len(inclus)
    corps = ", ".join(inclus) if inclus else f"{len(noms)} produits"
    message = _sans_accents(debut + corps + (f" +{reste} autre(s)" if inclus and reste else "") + fin)
    _envoyer_a_destinataires([numero_international(numero)], message[:160], TypeEvenement.RETOUR_STOCK)


# ---------- Produits habituels ----------


def ajouter_habituel(formation_sanitaire, produit, quantite=1):
    quantite = max(1, int(quantite or 1))
    habituel, cree = ProduitHabituel.objects.get_or_create(
        formation_sanitaire=formation_sanitaire, produit=produit, defaults={"quantite": quantite}
    )
    return habituel, cree


def retirer_habituel(formation_sanitaire, produit):
    return ProduitHabituel.objects.filter(formation_sanitaire=formation_sanitaire, produit=produit).delete()[0]


def modifier_quantites_habituelles(formation_sanitaire, quantites):
    """`quantites` : {produit_id: quantité}. Une quantité à 0 retire le produit."""
    for habituel in ProduitHabituel.objects.filter(formation_sanitaire=formation_sanitaire):
        if habituel.produit_id not in quantites:
            continue
        quantite = quantites[habituel.produit_id]
        if quantite <= 0:
            habituel.delete()
        elif quantite != habituel.quantite:
            habituel.quantite = quantite
            habituel.save(update_fields=["quantite"])


def produits_les_plus_commandes(formation_sanitaire, limite=10):
    """Produits que la FOSA a le plus commandés (en nombre de commandes), pour
    pré-remplir sa liste : [(produit, quantité moyenne)]."""
    from commandes.models import LigneCommande, StatutCommande

    lignes = (
        LigneCommande.objects.servies()
        .filter(
            commande__formation_sanitaire=formation_sanitaire,
            commande__statut__in=[StatutCommande.CONFIRMEE, StatutCommande.PAYEE],
        )
        .values("produit_id")
        .annotate(nb=Count("commande", distinct=True), total=Sum("quantite"))
        .order_by("-nb", "-total")[:limite]
    )
    produits = Produit.objects.in_bulk([ligne["produit_id"] for ligne in lignes])
    return [
        (produits[ligne["produit_id"]], max(1, round(ligne["total"] / ligne["nb"])))
        for ligne in lignes
        if ligne["produit_id"] in produits
    ]


def preremplir_habituels(formation_sanitaire):
    """Ajoute à la liste les produits les plus commandés qui n'y sont pas encore."""
    ajoutes = 0
    for produit, quantite in produits_les_plus_commandes(formation_sanitaire):
        _habituel, cree = ajouter_habituel(formation_sanitaire, produit, quantite)
        ajoutes += cree
    return ajoutes


def mettre_habituels_au_panier(formation_sanitaire):
    """Ajoute au panier chaque produit habituel disponible, à sa quantité habituelle
    (s'ajoute à ce qui est déjà au panier, plafonnée au stock). Retourne
    (ajoutés, réduits, indisponibles) : listes de noms."""
    from commandes.services import ajouter_produit, get_panier

    panier = get_panier(formation_sanitaire)
    deja = dict(panier.lignes.values_list("produit_id", "quantite"))
    ajoutes, reduits, indisponibles = [], [], []
    with transaction.atomic():
        for habituel in ProduitHabituel.objects.filter(formation_sanitaire=formation_sanitaire).select_related("produit"):
            produit = habituel.produit
            if not produit.en_stock or produit.magasin not in MAGASINS_CATALOGUE:
                indisponibles.append(produit.nom)
                continue
            total = deja.get(produit.pk, 0) + habituel.quantite
            if total > produit.stock_disponible:
                total = produit.stock_disponible
                reduits.append(produit.nom)
            else:
                ajoutes.append(produit.nom)
            ajouter_produit(panier, produit, total)
    return ajoutes, reduits, indisponibles


# ---------- Suggestions ----------

FENETRE_SUGGESTIONS_JOURS = 90


def suggestions(formation_sanitaire, exclure_ids=(), limite=6):
    """Produits à proposer à la FOSA, commandables et absents de `exclure_ids` :
    1. souvent commandés avec ce qu'elle a au panier (par les autres FOSA) ;
    2. puis les plus commandés dans son district ces 90 derniers jours.
    Retourne [(produit, raison)]."""
    from commandes.models import LigneCommande, StatutCommande

    exclure = set(exclure_ids)
    debut = timezone.now() - timedelta(days=FENETRE_SUGGESTIONS_JOURS)
    effectives = LigneCommande.objects.servies().filter(
        commande__statut__in=[StatutCommande.CONFIRMEE, StatutCommande.PAYEE],
        commande__date_confirmation__gte=debut,
    )
    commandables = set(produits_commandables().values_list("pk", flat=True))
    resultat = []

    def retenir(produit_ids, raison):
        for produit_id in produit_ids:
            if len(resultat) >= limite:
                return
            if produit_id in exclure or produit_id not in commandables:
                continue
            exclure.add(produit_id)
            resultat.append((produit_id, raison))

    if exclure_ids:
        # Commandes qui contiennent au moins un produit du panier : les autres produits
        # de ces commandes, classés par nombre de commandes où ils apparaissent.
        commandes_liees = effectives.filter(produit_id__in=list(exclure_ids)).values("commande_id")
        ensemble = (
            effectives.filter(commande_id__in=commandes_liees)
            .exclude(produit_id__in=list(exclure_ids))
            .values("produit_id")
            .annotate(nb=Count("commande", distinct=True))
            .order_by("-nb")
            .values_list("produit_id", flat=True)[:30]
        )
        retenir(ensemble, "Souvent commandé avec votre panier")

    if formation_sanitaire.district:
        district = (
            effectives.filter(commande__formation_sanitaire__district=formation_sanitaire.district)
            .values("produit_id")
            .annotate(nb=Count("commande__formation_sanitaire", distinct=True))
            .order_by("-nb")
            .values_list("produit_id", flat=True)[:30]
        )
        retenir(district, f"Commandé dans le district de {formation_sanitaire.district}")

    produits = Produit.objects.select_related("rayon").in_bulk([pid for pid, _r in resultat])
    sortie = []
    for produit_id, raison in resultat:
        produit = produits[produit_id]
        produit.raison_suggestion = raison
        sortie.append(produit)
    return sortie


# ---------- Commande mensuelle programmée ----------


def programmer_commande_mensuelle(formation_sanitaire, jour, active=True):
    try:
        jour = int(jour)
    except (TypeError, ValueError):
        raise ValueError("Choisissez un jour du mois.")
    if not 1 <= jour <= 28:
        raise ValueError("Choisissez un jour entre le 1er et le 28 (tous les mois en ont au moins 28).")
    programme, _ = CommandeMensuelle.objects.update_or_create(
        formation_sanitaire=formation_sanitaire, defaults={"jour_du_mois": jour, "active": bool(active)}
    )
    return programme


def preparer_si_echue(formation_sanitaire, aujourdhui=None):
    """Prépare la commande du mois si le jour choisi est atteint et qu'elle ne l'a pas
    encore été ce mois-ci. Appelée à l'ouverture des pages de la FOSA (pas de tâche
    planifiée sur l'hébergement) : la commande est donc prête dès sa première visite
    après le jour choisi. Retourne le résultat de mettre_habituels_au_panier, ou None."""
    aujourdhui = aujourdhui or timezone.localdate()
    mois = aujourdhui.replace(day=1)
    with transaction.atomic():
        programme = (
            CommandeMensuelle.objects.select_for_update()
            .filter(formation_sanitaire=formation_sanitaire, active=True)
            .first()
        )
        if (
            programme is None
            or aujourdhui.day < programme.jour_du_mois
            or programme.dernier_mois_prepare == mois
        ):
            return None
        # Marqué avant de remplir : deux pages ouvertes en même temps ne remplissent pas deux fois.
        programme.dernier_mois_prepare = mois
        programme.save(update_fields=["dernier_mois_prepare"])
    if not ProduitHabituel.objects.filter(formation_sanitaire=formation_sanitaire).exists():
        return None
    return mettre_habituels_au_panier(formation_sanitaire)
