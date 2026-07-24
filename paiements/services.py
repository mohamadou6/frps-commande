from django.utils import timezone

from commandes.models import StatutCommande

from .gateways import get_payment_gateway
from .models import MethodePaiement, Paiement, StatutPaiement


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
