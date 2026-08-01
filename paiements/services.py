from decimal import Decimal, InvalidOperation

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


def mettre_a_jour_paiement(commande, montant_paye_brut, user):
    """Saisie manuelle par le personnel comptabilité du montant reçu pour une
    commande payée hors application (espèces). Ne touche pas au statut de la
    commande (cycle de vie de la commande) : l'état de paiement est indépendant,
    porté par Paiement.montant_paye/etat."""
    if commande.statut not in (StatutCommande.CONFIRMEE, StatutCommande.PAYEE):
        raise ValueError("Seule une commande confirmée peut avoir un état de paiement.")

    try:
        montant_paye = Decimal(str(montant_paye_brut).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise ValueError("Montant invalide.")

    if montant_paye < 0:
        raise ValueError("Le montant payé ne peut pas être négatif.")
    if montant_paye > commande.montant_total:
        raise ValueError(f"Le montant payé ne peut pas dépasser le total de la commande ({commande.montant_total} FCFA).")

    paiement, _ = Paiement.objects.get_or_create(
        commande=commande,
        defaults={"montant": commande.montant_total, "methode": MethodePaiement.ESPECES},
    )
    paiement.montant_paye = montant_paye
    paiement.date_maj_paiement = timezone.now()
    paiement.maj_par = user
    paiement.save(update_fields=["montant_paye", "date_maj_paiement", "maj_par"])
    return montant_paye
