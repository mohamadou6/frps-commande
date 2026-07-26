import unicodedata

from django.conf import settings
from django.db.models import Q
from django.urls import reverse

from .backends import get_sms_backend
from .models import Notification, SMSLog, StatutEnvoi, TypeEvenement, WhatsAppLog
from .whatsapp import get_whatsapp_backend


def _sans_accents(texte):
    """Retire les accents pour permettre l'encodage SMS GSM-7 (160 car./segment)
    au lieu d'UCS-2 (70 car./segment) : messages plus courts, moins chers, plus
    vite livrés, sans perte de compréhension à l'écrit."""
    nfkd = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _envoyer_a_destinataires(destinataires, message, type_evenement, commande=None):
    backend = get_sms_backend()
    for numero in destinataires:
        if not numero:
            continue
        try:
            backend.send(numero, message)
            SMSLog.objects.create(
                destinataire=numero,
                message=message,
                type_evenement=type_evenement,
                statut_envoi=StatutEnvoi.ENVOYE,
                commande=commande,
            )
        except Exception as exc:  # noqa: BLE001 - on journalise toute erreur d'envoi
            SMSLog.objects.create(
                destinataire=numero,
                message=message,
                type_evenement=type_evenement,
                statut_envoi=StatutEnvoi.ECHEC,
                commande=commande,
                detail_erreur=str(exc),
            )


# Un SMS concaténé (2+ segments) s'est révélé peu fiable sur la route Twilio vers
# les numéros testés (message accepté mais jamais livré), alors qu'un SMS à segment
# unique est systématiquement livré en quelques secondes. On garde donc chaque SMS
# sous cette limite quel que soit le nombre de produits/quantités de la commande,
# quitte à résumer si le détail complet ne rentre pas (le PDF/l'appli a le détail).
_SMS_SEGMENT_MAX = 155


def _construire_message(entete, commande, cloture):
    lignes = list(commande.lignes.select_related("produit"))

    prefixe = _sans_accents(f"{entete} {commande.formation_sanitaire.nom}: ")
    suffixe = _sans_accents(f". Total {commande.montant_total} FCFA. {cloture}")
    items_texte = [_sans_accents(f"{ligne.produit.nom} x{ligne.quantite}") for ligne in lignes]

    # Essai avec le détail complet : si ça tient dans un segment, on garde tel quel.
    message_complet = prefixe + ", ".join(items_texte) + suffixe
    if not items_texte or len(message_complet) <= _SMS_SEGMENT_MAX:
        return message_complet

    # Sinon on ajoute les produits un par un, en vérifiant à chaque étape la longueur
    # FINALE (mention de troncature comprise) pour ne jamais dépasser un segment.
    inclus = []
    for i, item in enumerate(items_texte):
        restants = len(items_texte) - (i + 1)
        mention = f" +{restants} autre(s) (detail dans l'appli/PDF)" if restants else ""
        candidat = prefixe + ", ".join(inclus + [item]) + mention + suffixe
        if len(candidat) > _SMS_SEGMENT_MAX:
            break
        inclus.append(item)

    if not inclus:
        detail = f"{len(items_texte)} produits (detail dans l'appli/PDF)"
    else:
        restants = len(items_texte) - len(inclus)
        detail = ", ".join(inclus) + (f" +{restants} autre(s) (detail dans l'appli/PDF)" if restants else "")

    return prefixe + detail + suffixe


def _formatter_lignes_complet(commande):
    """Détail complet des produits, sans contrainte de longueur (pour la notification
    interne à l'application, contrairement au SMS)."""
    return ", ".join(
        f"{ligne.produit.nom} x{ligne.quantite}"
        for ligne in commande.lignes.select_related("produit")
    )


def notifier_nouvelle_commande(commande):
    from accounts.models import Role, User

    # L'admin FRPS supervise tout : il reçoit aussi les SMS destinés au personnel_stock.
    numeros = User.objects.filter(
        Q(role=Role.PERSONNEL_STOCK) | Q(role=Role.ADMIN), is_active=True
    ).exclude(telephone="").values_list("telephone", flat=True)

    message = _construire_message(f"Cde #{commande.pk}", commande, "Editer la Facture sur Sage.")
    _envoyer_a_destinataires(numeros, message, TypeEvenement.NOUVELLE_COMMANDE, commande=commande)

    Notification.objects.create(
        role_cible=Role.PERSONNEL_STOCK,
        type_evenement=TypeEvenement.NOUVELLE_COMMANDE,
        commande=commande,
        message=(
            f"Nouvelle commande #{commande.pk} de {commande.formation_sanitaire.nom} : "
            f"{_formatter_lignes_complet(commande)}. Total : {commande.montant_total} FCFA."
        ),
    )


def notifier_paiement_confirme(commande):
    from accounts.models import Role, User

    # L'admin FRPS supervise tout : il reçoit aussi les SMS destinés au personnel_comptabilite.
    numeros = User.objects.filter(
        Q(role=Role.PERSONNEL_COMPTABILITE) | Q(role=Role.ADMIN), is_active=True
    ).exclude(telephone="").values_list("telephone", flat=True)

    message = _construire_message(f"Paiement recu #{commande.pk}", commande, "Recu SVP.")
    _envoyer_a_destinataires(numeros, message, TypeEvenement.PAIEMENT_CONFIRME, commande=commande)

    Notification.objects.create(
        role_cible=Role.PERSONNEL_COMPTABILITE,
        type_evenement=TypeEvenement.PAIEMENT_CONFIRME,
        commande=commande,
        message=(
            f"Paiement reçu pour la commande #{commande.pk} de {commande.formation_sanitaire.nom} : "
            f"{_formatter_lignes_complet(commande)}. Total : {commande.montant_total} FCFA."
        ),
    )


def notifier_commande_validee_whatsapp(commande):
    """Envoie le PDF de la commande validée aux numéros WhatsApp configurés."""
    from .pdf import generer_pdf_commande, generer_token_pdf

    numeros = [n.strip() for n in settings.WHATSAPP_NOTIFICATION_NUMBERS if n.strip()]
    if not numeros:
        return

    pdf_bytes = generer_pdf_commande(commande)
    filename = f"commande_{commande.pk}.pdf"
    caption = (
        f"Commande #{commande.pk} validée - {commande.formation_sanitaire.nom} "
        f"({commande.montant_total} FCFA)"
    )
    token = generer_token_pdf(commande.pk)
    chemin_pdf = reverse("commandes:pdf", args=[commande.pk, token])
    media_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{chemin_pdf}"
    backend = get_whatsapp_backend()

    for numero in numeros:
        try:
            backend.send_document(numero, pdf_bytes, filename, caption, media_url=media_url)
            WhatsAppLog.objects.create(destinataire=numero, commande=commande, statut_envoi=StatutEnvoi.ENVOYE)
        except Exception as exc:  # noqa: BLE001 - on journalise toute erreur d'envoi
            WhatsAppLog.objects.create(
                destinataire=numero,
                commande=commande,
                statut_envoi=StatutEnvoi.ECHEC,
                detail_erreur=str(exc),
            )
