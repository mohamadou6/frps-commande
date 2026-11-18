"""Recherche dans l'historique des commandes (page « Mes commandes » des FOSA)."""

from decimal import Decimal, InvalidOperation

from django.db.models import F, Q, Sum
from django.utils.dateparse import parse_date

from .models import EtapeTraitement, StatutCommande

STATUTS_EFFECTIFS = [StatutCommande.CONFIRMEE, StatutCommande.PAYEE]

TRIS = {
    "recent": ("Plus récentes d'abord", ["-date_creation"]),
    "ancien": ("Plus anciennes d'abord", ["date_creation"]),
    "montant_desc": ("Montant décroissant", ["-montant_total", "-date_creation"]),
    "montant_asc": ("Montant croissant", ["montant_total", "-date_creation"]),
}

ETATS_PAIEMENT = [("non_payee", "Non payée"), ("partielle", "Partielle"), ("payee", "Payée")]

CHAMPS = ("numero", "debut", "fin", "montant_min", "montant_max", "produit", "etape", "paiement", "tri")


def _montant(valeur):
    texte = (valeur or "").replace(" ", "").replace(" ", "").replace(",", ".")
    if not texte:
        return None
    try:
        montant = Decimal(texte)
    except InvalidOperation:
        raise ValueError(f"Montant illisible : « {valeur} ».")
    if montant < 0:
        raise ValueError("Un montant ne peut pas être négatif.")
    return montant


def filtrer_commandes(commandes, params):
    """Applique les critères de recherche à `commandes`.

    Retourne (commandes filtrées et triées, critères retenus, liste d'erreurs). Un
    critère illisible est ignoré avec un message plutôt que de vider la liste : la
    FOSA voit ce qui n'a pas été compris."""
    criteres = {cle: (params.get(cle) or "").strip() for cle in CHAMPS}
    erreurs = []

    if criteres["numero"]:
        numero = criteres["numero"].lstrip("#")
        if numero.isdigit():
            commandes = commandes.filter(pk=int(numero))
        else:
            erreurs.append(f"Numéro de commande illisible : « {criteres['numero']} ».")

    for cle, lookup, libelle in (("debut", "date_creation__date__gte", "début"), ("fin", "date_creation__date__lte", "fin")):
        if criteres[cle]:
            jour = parse_date(criteres[cle])
            if jour is None:
                erreurs.append(f"Date de {libelle} illisible.")
            else:
                commandes = commandes.filter(**{lookup: jour})

    for cle, lookup in (("montant_min", "montant_total__gte"), ("montant_max", "montant_total__lte")):
        try:
            montant = _montant(criteres[cle])
        except ValueError as exc:
            erreurs.append(str(exc))
        else:
            if montant is not None:
                commandes = commandes.filter(**{lookup: montant})

    if criteres["produit"]:
        # Lignes servies seulement : un produit demandé hors connexion mais jamais servi
        # (quantité 0) ne fait pas partie de la commande.
        commandes = commandes.filter(
            lignes__produit__nom__icontains=criteres["produit"], lignes__quantite__gt=0
        ).distinct()

    if criteres["etape"] in EtapeTraitement.values:
        commandes = commandes.filter(statut__in=STATUTS_EFFECTIFS, etape=criteres["etape"])

    # Mêmes règles que Paiement.etat : un solde de moins d'1 FCFA compte comme réglé.
    if criteres["paiement"] == "payee":
        commandes = commandes.filter(statut__in=STATUTS_EFFECTIFS, paiement__montant_paye__gt=0).filter(
            paiement__montant_paye__gt=F("montant_total") - 1
        )
    elif criteres["paiement"] == "partielle":
        commandes = commandes.filter(
            statut__in=STATUTS_EFFECTIFS,
            paiement__montant_paye__gt=0,
            paiement__montant_paye__lte=F("montant_total") - 1,
        )
    elif criteres["paiement"] == "non_payee":
        commandes = commandes.filter(statut__in=STATUTS_EFFECTIFS).filter(
            Q(paiement__isnull=True) | Q(paiement__montant_paye__lte=0)
        )

    if criteres["tri"] not in TRIS:
        criteres["tri"] = "recent"
    commandes = commandes.order_by(*TRIS[criteres["tri"]][1])
    return commandes, criteres, erreurs


def resume(commandes):
    """Nombre de commandes trouvées et montant total de celles qui ont été validées."""
    total = commandes.filter(statut__in=STATUTS_EFFECTIFS).aggregate(total=Sum("montant_total"))["total"]
    return {"nombre": commandes.count(), "montant": total or Decimal("0")}
