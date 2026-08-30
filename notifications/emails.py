"""Envoi par email des évènements de commande au personnel FRPS.

Complète le SMS (payant, tronqué à un segment) et le push (éphémère, lié à un
appareil) : l'email n'a pas de limite de longueur et peut porter le PDF de la
commande en pièce jointe, ce que la FOSA devait jusqu'ici partager à la main.
"""

import logging

from django.core.mail import EmailMessage, get_connection

from frps_project.formatage import formater_montant, formater_prix

from .models import EmailLog, StatutEnvoi, TypeEvenement
from .pdf import generer_pdf_commande

logger = logging.getLogger(__name__)


def destinataires_personnel_frps():
    """Emails du personnel FRPS actif : tous les rôles SAUF les formations
    sanitaires, puisque c'est la FOSA elle-même qui valide la commande.

    Les comptes sans email renseigné sont forcément exclus — c'est le même piège
    que pour le SMS (voir notifications/services.py) : si aucun compte du rôle n'a
    d'adresse, rien ne part. D'où l'avertissement journalisé par l'appelant quand
    la liste ressort vide, pour que le silence ne passe pas inaperçu.
    """
    from accounts.models import Role, User

    return sorted(
        set(
            User.objects.filter(is_active=True)
            .exclude(role=Role.FORMATION_SANITAIRE)
            .exclude(email="")
            .values_list("email", flat=True)
        )
    )


def _corps_nouvelle_commande(commande):
    formation = commande.formation_sanitaire
    lignes = list(commande.lignes.select_related("produit"))

    localisation = " - ".join(p for p in (formation.district, formation.region) if p)
    entete = [
        f"Nouvelle commande #{commande.pk} validée par {formation.nom}"
        + (f" ({localisation})" if localisation else "")
        + ".",
        "",
    ]
    if formation.telephone_contact:
        entete.append(f"Contact FOSA : {formation.telephone_contact}")
    if commande.date_confirmation:
        entete.append(f"Validée le : {commande.date_confirmation.strftime('%d/%m/%Y à %H:%M')}")
    entete.append("")

    detail = [f"Produits commandés ({len(lignes)}) :"]
    for ligne in lignes:
        detail.append(
            f"  - {ligne.produit.nom} : {ligne.quantite} x {formater_prix(ligne.prix_unitaire_snapshot)}"
            f" = {formater_montant(ligne.sous_total)} FCFA"
        )

    pied = [
        "",
        f"Montant total : {formater_montant(commande.montant_total)} FCFA",
        "",
        "Le bon de commande est joint à cet email au format PDF.",
        "",
        "-- ",
        "Message automatique de l'application Commande FRPS.",
    ]
    return "\n".join(entete + detail + pied)


def envoyer_email_nouvelle_commande(commande):
    """Envoie le récapitulatif de la commande, PDF joint, à tout le personnel FRPS.

    Un envoi par destinataire plutôt qu'un envoi groupé : une adresse invalide ne
    prive alors pas les autres du message, et chaque issue est tracée séparément
    dans EmailLog. Aucune exception ne remonte — l'appelant valide une commande,
    un relais SMTP en panne ne doit pas la faire échouer.
    """
    destinataires = destinataires_personnel_frps()
    if not destinataires:
        logger.warning(
            "Commande #%s : aucun email envoyé, aucun compte FRPS actif (hors FOSA) "
            "n'a d'adresse renseignée. Compléter les emails dans /admin/accounts/user/.",
            commande.pk,
        )
        return 0

    sujet = f"[Commande FRPS] Nouvelle commande #{commande.pk} - {commande.formation_sanitaire.nom}"
    corps = _corps_nouvelle_commande(commande)

    # Le PDF n'est pas indispensable à l'alerte : s'il échoue, on prévient quand
    # même, sans pièce jointe, plutôt que de ne rien envoyer du tout.
    pdf = None
    try:
        pdf = generer_pdf_commande(commande)
    except Exception:  # noqa: BLE001 - le PDF ne doit pas bloquer la notification
        logger.exception("Commande #%s : PDF non généré, email envoyé sans pièce jointe", commande.pk)

    connexion = get_connection(fail_silently=False)
    envoyes = 0
    for adresse in destinataires:
        try:
            message = EmailMessage(subject=sujet, body=corps, to=[adresse], connection=connexion)
            if pdf:
                message.attach(f"commande_{commande.pk}.pdf", pdf, "application/pdf")
            message.send(fail_silently=False)
            EmailLog.objects.create(
                destinataire=adresse,
                sujet=sujet,
                type_evenement=TypeEvenement.NOUVELLE_COMMANDE,
                statut_envoi=StatutEnvoi.ENVOYE,
                commande=commande,
            )
            envoyes += 1
        except Exception as exc:  # noqa: BLE001 - on journalise toute erreur d'envoi
            EmailLog.objects.create(
                destinataire=adresse,
                sujet=sujet,
                type_evenement=TypeEvenement.NOUVELLE_COMMANDE,
                statut_envoi=StatutEnvoi.ECHEC,
                commande=commande,
                detail_erreur=str(exc),
            )
            logger.warning("Commande #%s : échec de l'email vers %s (%s)", commande.pk, adresse, exc)
    return envoyes
