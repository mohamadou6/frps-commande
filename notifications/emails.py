"""Envoi par email des évènements de commande au personnel FRPS.

Complète le SMS (payant, tronqué à un segment) et le push (éphémère, lié à un
appareil) : l'email n'a pas de limite de longueur et peut porter le PDF de la
commande en pièce jointe, ce que la FOSA devait jusqu'ici partager à la main.
"""

import logging

from django.core.mail import EmailMessage, get_connection

from frps_project.formatage import formater_montant, formater_prix

from .models import DestinataireEmail, EmailLog, StatutEnvoi, TypeEvenement
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

    comptes = (
        User.objects.filter(is_active=True)
        .exclude(role=Role.FORMATION_SANITAIRE)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    # + les adresses ajoutées dans Paramètres pour les commandes (boîte de service…).
    return fusionner_adresses(comptes, DestinataireEmail.objects.pour("recoit_commandes").values_list("email", flat=True))


def fusionner_adresses(*listes):
    """Adresses sans doublon, la casse ne comptant pas (Jean@x.cm = jean@x.cm)."""
    vues = {}
    for liste in listes:
        for adresse in liste:
            if adresse:
                vues.setdefault(adresse.strip().lower(), adresse.strip())
    return sorted(vues.values(), key=str.lower)


def _corps_nouvelle_commande(commande):
    formation = commande.formation_sanitaire
    lignes = list(commande.lignes.servies().select_related("produit"))

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
            f" = {formater_prix(ligne.sous_total)} FCFA"
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

    pieces = [(f"commande_{commande.pk}.pdf", pdf, "application/pdf")] if pdf else []
    return envoyer_un_par_un(
        destinataires, sujet, corps, TypeEvenement.NOUVELLE_COMMANDE, commande=commande, pieces=pieces
    )


def envoyer_un_par_un(destinataires, sujet, corps, type_evenement, commande=None, pieces=()):
    """Un envoi par destinataire plutôt qu'un envoi groupé : une adresse invalide ne
    prive pas les autres du message, et chaque issue est tracée dans EmailLog. Aucune
    exception ne remonte. Retourne le nombre d'envois acceptés par le relais."""
    connexion = get_connection(fail_silently=False)
    envoyes = 0
    for adresse in destinataires:
        try:
            message = EmailMessage(subject=sujet, body=corps, to=[adresse], connection=connexion)
            for nom, contenu, type_mime in pieces:
                message.attach(nom, contenu, type_mime)
            message.send(fail_silently=False)
            EmailLog.objects.create(
                destinataire=adresse,
                sujet=sujet[:255],
                type_evenement=type_evenement,
                statut_envoi=StatutEnvoi.ENVOYE,
                commande=commande,
            )
            envoyes += 1
        except Exception as exc:  # noqa: BLE001 - on journalise toute erreur d'envoi
            EmailLog.objects.create(
                destinataire=adresse,
                sujet=sujet[:255],
                type_evenement=type_evenement,
                statut_envoi=StatutEnvoi.ECHEC,
                commande=commande,
                detail_erreur=str(exc),
            )
            logger.warning("%s : échec de l'email vers %s (%s)", sujet, adresse, exc)
    return envoyes


def envoyer_email_reclamation(reclamation, rouverte=False):
    """Prévient par e-mail les adresses cochées « Réclamations » dans Paramètres.

    Seules ces adresses reçoivent les réclamations (pas tout le personnel) : c'est
    l'admin FRPS qui choisit qui les traite. Liste vide = aucun envoi, journalisé."""
    from django.conf import settings
    from django.urls import reverse

    destinataires = fusionner_adresses(
        DestinataireEmail.objects.pour("recoit_reclamations").values_list("email", flat=True)
    )
    if not destinataires:
        logger.warning(
            "Réclamation #%s : aucun email envoyé, aucune adresse « Réclamations » active "
            "dans Paramètres > E-mails.",
            reclamation.pk,
        )
        return 0

    fosa = reclamation.formation_sanitaire
    lien = settings.PUBLIC_BASE_URL.rstrip("/") + reverse("reclamations:detail", args=[reclamation.pk])
    if rouverte:
        sujet = f"[Commande FRPS] Réclamation #{reclamation.pk} rouverte - {fosa.nom}"
        dernier = reclamation.messages.filter(de_la_fosa=True).order_by("-date").first()
        intro = [f"{fosa.nom} a rouvert la réclamation #{reclamation.pk} : le problème n'est pas réglé.", ""]
        texte = dernier.texte if dernier and dernier.texte else "(photo jointe, sans texte)"
        photos = list(dernier.photos.all()) if dernier else []
    else:
        sujet = f"[Commande FRPS] Nouvelle réclamation #{reclamation.pk} - {fosa.nom}"
        intro = [f"Nouvelle réclamation #{reclamation.pk} de {fosa.nom}.", ""]
        texte = reclamation.description
        photos = list(reclamation.photos.filter(message__isnull=True))

    localisation = " - ".join(p for p in (fosa.district, fosa.region) if p)
    lignes = intro + [f"Motif : {reclamation.get_motif_display()}"]
    if reclamation.commande_id:
        lignes.append(f"Commande concernée : #{reclamation.commande_id}")
    if localisation:
        lignes.append(f"Localisation : {localisation}")
    if fosa.telephone_contact:
        lignes.append(f"Contact FOSA : {fosa.telephone_contact}")
    lignes += ["", "Message de la FOSA :", texte, ""]
    if photos:
        lignes.append(f"{len(photos)} photo(s) jointe(s) à cet email.")
    lignes += [
        "",
        f"Répondre ou changer le statut : {lien}",
        "",
        "-- ",
        "Message automatique de l'application Commande FRPS.",
    ]
    pieces = [
        (f"reclamation_{reclamation.pk}_photo_{rang}.jpg", bytes(photo.contenu), "image/jpeg")
        for rang, photo in enumerate(photos, start=1)
    ]
    return envoyer_un_par_un(
        destinataires,
        sujet,
        "\n".join(lignes),
        TypeEvenement.RECLAMATION,
        commande=reclamation.commande,
        pieces=pieces,
    )


def envoyer_email_test(adresse):
    """E-mail d'essai depuis Paramètres : prouve que l'adresse est bonne et que le
    relais accepte l'envoi (pas qu'il est lu : vérifier aussi les indésirables)."""
    return envoyer_un_par_un(
        [adresse],
        "[Commande FRPS] E-mail de test",
        "Cette adresse est bien paramétrée pour recevoir les e-mails de l'application "
        "Commande FRPS.\n\n-- \nMessage automatique de l'application Commande FRPS.",
        TypeEvenement.EMAIL_TEST,
    )
