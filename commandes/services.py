import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from catalogue.models import Produit

from .models import Commande, LigneCommande, StatutCommande

logger = logging.getLogger(__name__)


class StockInsuffisantError(Exception):
    pass


class DemandeInvalideError(ValueError):
    """Demande hors connexion que le serveur ne peut pas accepter, même en la renvoyant."""


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
        _debiter_stock(commande.lignes.select_related("produit"))
        commande.recalculer_montant()
        commande.statut = StatutCommande.CONFIRMEE
        commande.date_confirmation = timezone.now()
        commande.save(update_fields=["statut", "date_confirmation"])

    notifier_nouvelle_commande(commande)
    return commande


def _debiter_stock(lignes):
    """À appeler dans une transaction : une ligne refusée lève StockInsuffisantError,
    ce qui annule aussi les débits des lignes précédentes."""
    for ligne in lignes:
        # Débit atomique conditionné sur le stock au moment de l'update (évite qu'une
        # commande concurrente ne fasse passer le stock sous zéro entre la vérification
        # et le débit).
        debite = Produit.objects.filter(
            pk=ligne.produit_id, stock_disponible__gte=ligne.quantite
        ).update(stock_disponible=F("stock_disponible") - ligne.quantite)
        if not debite:
            raise StockInsuffisantError(
                f"Stock insuffisant pour {ligne.produit.nom} "
                f"(disponible : {ligne.produit.stock_disponible})"
            )


# ---------- Commandes préparées hors connexion ----------
# Le téléphone de la FOSA garde la commande tant qu'il n'a pas de réseau, puis
# l'envoie (Background Sync ou page rouverte). Ce qu'elle a vu hors ligne — stock et
# prix du catalogue enregistré — a pu changer : le serveur ne reprend du téléphone que
# les produits et les quantités demandées, et décide du reste au moment où la demande
# arrive.


def synchroniser_demande(formation_sanitaire, uuid_client, quantites):
    """Reçoit puis valide une demande hors connexion. Retourne (commande, reçue_maintenant).

    `quantites` : {produit_id: quantité demandée}. Renvoyer la même demande (même
    `uuid_client`) ne crée rien de plus et ne débite rien de plus : on retrouve la
    commande, et on termine sa validation si un envoi précédent l'avait laissée en
    route.
    """
    commande, recue_maintenant = recevoir_demande(formation_sanitaire, uuid_client, quantites)
    return valider_demande(commande), recue_maintenant


def recevoir_demande(formation_sanitaire, uuid_client, quantites):
    """Enregistre la demande telle qu'envoyée, sans toucher au stock.

    Séparée de la validation pour que la demande soit acquise dès sa réception : si
    la validation échoue ensuite, la commande reste « en attente de validation » et
    le renvoi automatique du téléphone la reprend, sans rien perdre ni doubler.
    """
    existante = Commande.objects.filter(uuid_client=uuid_client).first()
    if existante is not None:
        return _demande_du_meme_compte(existante, formation_sanitaire), False

    # Un produit supprimé du catalogue depuis la préparation est ignoré : le
    # téléphone, qui a gardé sa demande, voit qu'il manque dans la réponse.
    produits = Produit.objects.in_bulk(list(quantites))
    if not produits:
        raise DemandeInvalideError("Aucun des produits demandés n'existe plus au catalogue.")

    try:
        with transaction.atomic():
            commande = Commande.objects.create(
                formation_sanitaire=formation_sanitaire,
                statut=StatutCommande.EN_ATTENTE_SYNCHRO,
                uuid_client=uuid_client,
            )
            LigneCommande.objects.bulk_create(
                LigneCommande(
                    commande=commande,
                    produit=produit,
                    quantite=0,
                    quantite_demandee=quantites[produit_id],
                    prix_unitaire_snapshot=produit.prix_unitaire,
                )
                for produit_id, produit in produits.items()
            )
    except IntegrityError:
        # La même demande est arrivée deux fois en même temps (le service worker et la
        # page l'envoient chacun au retour du réseau) : l'autre requête l'a créée.
        existante = Commande.objects.get(uuid_client=uuid_client)
        return _demande_du_meme_compte(existante, formation_sanitaire), False
    return commande, True


def _demande_du_meme_compte(commande, formation_sanitaire):
    if commande.formation_sanitaire_id != formation_sanitaire.pk:
        # Message volontairement vague : ne rien révéler d'une commande d'une autre FOSA.
        raise DemandeInvalideError("Identifiant de demande déjà utilisé.")
    return commande


def valider_demande(commande):
    """Sert la demande avec le stock et les prix du moment, puis la confirme.

    Chaque ligne reçoit ce que le stock permet (jusqu'à 0) : refuser toute la commande
    pour un produit épuisé obligerait la FOSA à tout recommencer, alors qu'elle n'est
    plus devant son téléphone quand la demande part. Rien de servi : la commande est
    annulée, sans débit ni notification.
    """
    from notifications.services import notifier_nouvelle_commande

    with transaction.atomic():
        # garde : verrou sur la commande. Deux envois simultanés de la même demande
        # arrivent ici tous les deux ; le second attend, voit la commande déjà validée
        # et ne débite rien.
        commande = Commande.objects.select_for_update().get(pk=commande.pk)
        if commande.statut != StatutCommande.EN_ATTENTE_SYNCHRO:
            return commande

        lignes = list(commande.lignes.select_related("produit"))
        # garde : verrou sur les produits jusqu'au débit, sinon une commande concurrente
        # pourrait prendre le stock entre la lecture et le débit. Pris dans l'ordre des
        # clés : deux validations qui partagent des produits ne s'interbloquent pas.
        produits = {
            produit.pk: produit
            for produit in Produit.objects.select_for_update()
            .filter(pk__in=[ligne.produit_id for ligne in lignes])
            .order_by("pk")
        }
        for ligne in lignes:
            produit = produits[ligne.produit_id]
            disponible = produit.stock_disponible if produit.actif else 0
            ligne.quantite = min(ligne.quantite_demandee, disponible)
            ligne.prix_unitaire_snapshot = produit.prix_unitaire
        LigneCommande.objects.bulk_update(lignes, ["quantite", "prix_unitaire_snapshot"])

        servies = [ligne for ligne in lignes if ligne.quantite]
        _debiter_stock(servies)
        commande.recalculer_montant()
        if servies:
            commande.statut = StatutCommande.CONFIRMEE
            commande.date_confirmation = timezone.now()
        else:
            commande.statut = StatutCommande.ANNULEE
        commande.save(update_fields=["statut", "date_confirmation"])

    if commande.statut == StatutCommande.CONFIRMEE:
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
