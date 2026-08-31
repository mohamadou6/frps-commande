import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalogue.models import Produit

from .models import Commande, LigneCommande, StatutCommande

logger = logging.getLogger(__name__)


class StockInsuffisantError(Exception):
    pass


def get_panier(formation_sanitaire):
    """Retourne le panier (commande brouillon) en cours, en crée un si besoin."""
    commande, _ = Commande.objects.get_or_create(
        formation_sanitaire=formation_sanitaire,
        statut=StatutCommande.BROUILLON,
        defaults={},
    )
    return commande


def ajouter_produit(commande, produit, quantite):
    if quantite <= 0:
        raise ValueError("La quantité doit être positive")
    if quantite > produit.stock_disponible:
        raise StockInsuffisantError(
            f"Stock insuffisant pour {produit.nom} (disponible : {produit.stock_disponible})"
        )

    ligne, created = LigneCommande.objects.get_or_create(
        commande=commande,
        produit=produit,
        defaults={"quantite": quantite, "prix_unitaire_snapshot": produit.prix_unitaire},
    )
    if not created:
        ligne.quantite = quantite
        ligne.prix_unitaire_snapshot = produit.prix_unitaire
        ligne.save()

    commande.recalculer_montant()
    return ligne


def retirer_produit(commande, produit):
    commande.lignes.filter(produit=produit).delete()
    commande.recalculer_montant()


def confirmer_commande(commande):
    """Verrouille la commande, débite le stock, notifie le personnel FRPS chargé du stock."""
    from notifications.services import notifier_nouvelle_commande

    if commande.statut != StatutCommande.BROUILLON:
        raise ValueError("Seul un panier en brouillon peut être confirmé")
    if not commande.lignes.exists():
        raise ValueError("Le panier est vide")

    with transaction.atomic():
        # Débit atomique conditionné sur le stock au moment de l'update (évite qu'une
        # commande concurrente ne fasse passer le stock sous zéro entre la vérification
        # et le débit).
        for ligne in commande.lignes.select_related("produit"):
            debite = Produit.objects.filter(
                pk=ligne.produit_id, stock_disponible__gte=ligne.quantite
            ).update(stock_disponible=F("stock_disponible") - ligne.quantite)
            if not debite:
                raise StockInsuffisantError(
                    f"Stock insuffisant pour {ligne.produit.nom} "
                    f"(disponible : {ligne.produit.stock_disponible})"
                )

        commande.recalculer_montant()
        commande.statut = StatutCommande.CONFIRMEE
        commande.date_confirmation = timezone.now()
        commande.save(update_fields=["statut", "date_confirmation"])

    notifier_nouvelle_commande(commande)
    return commande


# Seuls ces statuts ont effectivement débité le stock (voir confirmer_commande).
# Un brouillon n'a jamais rien débité : le recréditer gonflerait le stock.
STATUTS_AYANT_DEBITE_LE_STOCK = (StatutCommande.CONFIRMEE, StatutCommande.PAYEE)


def supprimer_commande(commande):
    """Supprime une commande et remet en stock ce qu'elle avait débité.

    Sert à corriger une commande validée par erreur par une FOSA. Réservé à l'admin
    FRPS (voir la vue commandes.views.supprimer).

    La suppression seule ne restaure PAS le stock — il est débité à la confirmation,
    pas à la lecture. C'est toute la raison d'être de cette fonction : faire les deux
    dans une seule transaction, pour qu'un échec ne laisse jamais un stock recrédité
    sans commande supprimée, ni l'inverse.

    Les lignes, le paiement éventuel et les notifications internes disparaissent en
    cascade. Les SMSLog/EmailLog sont seulement détachés (`SET_NULL`) : ces envois ont
    réellement eu lieu et coûté de l'argent, la piste d'audit doit survivre.
    """
    with transaction.atomic():
        # verrou : empêche une suppression concurrente de recréditer le stock deux fois
        commande = Commande.objects.select_for_update().get(pk=commande.pk)
        reference = commande.pk
        restaure = []
        if commande.statut in STATUTS_AYANT_DEBITE_LE_STOCK:
            for ligne in commande.lignes.select_related("produit"):
                Produit.objects.filter(pk=ligne.produit_id).update(
                    stock_disponible=F("stock_disponible") + ligne.quantite
                )
                restaure.append((ligne.produit.nom, ligne.quantite))
        commande.delete()

    logger.warning(
        "Commande #%s supprimée (statut %s). Stock remis : %s",
        reference,
        commande.statut,
        ", ".join(f"{nom} +{q}" for nom, q in restaure) or "aucun (pas de débit)",
    )
    return reference
