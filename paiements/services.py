from decimal import Decimal, InvalidOperation

from django.utils import timezone

from commandes.models import StatutCommande

from .gateways import get_payment_gateway
from .models import MethodePaiement, Paiement, ReglementPaiement, StatutPaiement


def initier_paiement(commande):
    """Initie un paiement Orange Money (le client règle sur le compte Orange Money du FRPS)."""
    if commande.statut != StatutCommande.CONFIRMEE:
        raise ValueError("Seule une commande confirmée peut être payée")

    paiement, _ = Paiement.objects.get_or_create(
        commande=commande,
        defaults={"montant": commande.montant_total, "methode": MethodePaiement.ORANGE_MONEY},
    )
    gateway = get_payment_gateway()
    reference = gateway.initiate_payment(paiement)
    paiement.reference_transaction = reference
    paiement.save(update_fields=["reference_transaction"])
    return paiement


def payer_en_especes(commande):
    """Valide directement la commande en paiement espèces : aucune étape supplémentaire."""
    if commande.statut != StatutCommande.CONFIRMEE:
        raise ValueError("Seule une commande confirmée peut être payée")

    paiement, created = Paiement.objects.get_or_create(
        commande=commande,
        defaults={"montant": commande.montant_total, "methode": MethodePaiement.ESPECES},
    )
    if not created:
        paiement.methode = MethodePaiement.ESPECES
        paiement.save(update_fields=["methode"])

    return confirmer_paiement(paiement, succes=True)


def confirmer_paiement(paiement, succes: bool):
    from notifications.services import notifier_paiement_confirme

    paiement.statut = StatutPaiement.CONFIRME if succes else StatutPaiement.ECHOUE
    paiement.date_confirmation = timezone.now()
    paiement.save(update_fields=["statut", "date_confirmation"])

    if succes:
        commande = paiement.commande
        commande.statut = StatutCommande.PAYEE
        commande.save(update_fields=["statut"])
        notifier_paiement_confirme(commande)
        # Le PDF n'est plus envoyé automatiquement par WhatsApp (API Business trop
        # lourde à mettre en place) : la FOSA le télécharge et le partage elle-même
        # depuis son propre WhatsApp (voir commandes:telecharger_pdf).

    return paiement


def mettre_a_jour_paiement(commande, montant_verse_brut, user, methode=MethodePaiement.ESPECES):
    """Saisie manuelle par le personnel comptabilité d'un nouveau versement reçu
    pour une commande payée hors application (espèces). Chaque appel ajoute un
    ReglementPaiement (l'historique) et incrémente Paiement.montant_paye d'autant
    — il ne remplace pas le montant déjà enregistré, pour permettre plusieurs
    règlements partiels successifs jusqu'au paiement intégral. Ne touche pas au
    statut de la commande (cycle de vie de la commande) : l'état de paiement est
    indépendant, porté par Paiement.montant_paye/etat."""
    if commande.statut not in (StatutCommande.CONFIRMEE, StatutCommande.PAYEE):
        raise ValueError("Seule une commande confirmée peut avoir un état de paiement.")

    try:
        montant_verse = Decimal(str(montant_verse_brut).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise ValueError("Montant invalide.")

    if montant_verse <= 0:
        raise ValueError("Le montant versé doit être supérieur à 0.")

    if methode not in MethodePaiement.values:
        raise ValueError("Moyen de paiement invalide.")

    paiement, _ = Paiement.objects.get_or_create(
        commande=commande,
        defaults={"montant": commande.montant_total, "methode": MethodePaiement.ESPECES},
    )

    nouveau_total = paiement.montant_paye + montant_verse
    if nouveau_total > commande.montant_total:
        restant = commande.montant_total - paiement.montant_paye
        raise ValueError(
            f"Ce versement dépasse le solde restant dû ({restant} FCFA)."
        )

    ReglementPaiement.objects.create(paiement=paiement, montant=montant_verse, methode=methode, saisi_par=user)

    paiement.montant_paye = nouveau_total
    paiement.methode = methode
    paiement.date_maj_paiement = timezone.now()
    paiement.maj_par = user
    paiement.save(update_fields=["montant_paye", "methode", "date_maj_paiement", "maj_par"])
    return montant_verse
