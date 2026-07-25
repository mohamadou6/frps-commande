from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalogue.models import Produit

from .models import Commande, LigneCommande, StatutCommande


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
