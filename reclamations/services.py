import io
import logging
import warnings

from django.db import transaction
from django.utils import timezone

from commandes.models import StatutCommande

from .models import MessageReclamation, MotifReclamation, PhotoReclamation, Reclamation, StatutReclamation

logger = logging.getLogger(__name__)

LONGUEUR_MAX_TEXTE = 4000

# Photos : le téléphone les réduit déjà avant l'envoi (js/photos.js) ; ces limites
# protègent le serveur quand il ne l'a pas fait (vieux navigateur, envoi direct).
PHOTOS_MAX_PAR_ENVOI = 3
TAILLE_MAX_FICHIER = 12 * 1024 * 1024
PIXELS_MAX = 40_000_000  # ~ photo de 48 Mpx : au-delà, refus plutôt que d'ouvrir une « bombe »
COTE_MAX = 1600
QUALITE_JPEG = 80


def preparer_photo(fichier):
    """Vérifie qu'un fichier envoyé est bien une image et la réduit : grand côté à
    1600 px, JPEG, orientation du téléphone appliquée. Retourne (octets, largeur, hauteur).

    On ne garde jamais le fichier d'origine : réencoder élimine aussi tout contenu
    caché dans un faux « .jpg » et les métadonnées (position GPS de la photo)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    nom = getattr(fichier, "name", "photo")
    if fichier.size > TAILLE_MAX_FICHIER:
        raise ValueError(f"« {nom} » est trop lourde ({TAILLE_MAX_FICHIER // (1024 * 1024)} Mo au maximum).")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(fichier)
            if image.width * image.height > PIXELS_MAX:
                raise ValueError(f"« {nom} » est une image trop grande.")
            image = ImageOps.exif_transpose(image)
            image.load()
    except ValueError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError):
        raise ValueError(f"« {nom} » n'est pas une image lisible (formats acceptés : photo JPEG, PNG, WebP…).")

    if image.mode not in ("RGB", "L"):
        fond = Image.new("RGB", image.size, "white")
        image = image.convert("RGBA")
        fond.paste(image, mask=image.getchannel("A"))
        image = fond
    image.thumbnail((COTE_MAX, COTE_MAX))
    sortie = io.BytesIO()
    image.convert("RGB").save(sortie, "JPEG", quality=QUALITE_JPEG, optimize=True, progressive=True)
    return sortie.getvalue(), image.width, image.height


def _preparer_photos(fichiers):
    """Prépare toutes les photos AVANT d'écrire quoi que ce soit : une photo refusée
    ne doit pas laisser une réclamation enregistrée à moitié."""
    fichiers = [f for f in (fichiers or []) if f]
    if len(fichiers) > PHOTOS_MAX_PAR_ENVOI:
        raise ValueError(f"{PHOTOS_MAX_PAR_ENVOI} photos au maximum par envoi.")
    return [preparer_photo(f) for f in fichiers]


def _enregistrer_photos(reclamation, photos, message=None):
    PhotoReclamation.objects.bulk_create(
        PhotoReclamation(reclamation=reclamation, message=message, contenu=octets, largeur=largeur, hauteur=hauteur)
        for octets, largeur, hauteur in photos
    )


def _texte_propre(texte):
    texte = (texte or "").strip()
    if len(texte) > LONGUEUR_MAX_TEXTE:
        raise ValueError(f"Le message est trop long ({LONGUEUR_MAX_TEXTE} caractères au maximum).")
    return texte


def creer_reclamation(formation_sanitaire, auteur, motif, description, commande=None, photos=None):
    if motif not in MotifReclamation.values:
        raise ValueError("Choisissez le motif de la réclamation.")
    description = _texte_propre(description)
    if not description:
        raise ValueError("Décrivez le problème rencontré.")
    if commande is not None:
        if commande.formation_sanitaire_id != formation_sanitaire.pk:
            raise ValueError("Cette commande n'appartient pas à votre formation sanitaire.")
        if commande.statut == StatutCommande.BROUILLON:
            raise ValueError("Une réclamation ne peut porter que sur une commande validée.")

    photos = _preparer_photos(photos)

    with transaction.atomic():
        reclamation = Reclamation.objects.create(
            formation_sanitaire=formation_sanitaire,
            commande=commande,
            motif=motif,
            description=description,
        )
        _enregistrer_photos(reclamation, photos)
    logger.info("Réclamation #%s créée par %s", reclamation.pk, auteur)
    _prevenir_personnel(
        f"Nouvelle réclamation #{reclamation.pk}",
        f"{formation_sanitaire.nom} : {reclamation.get_motif_display()}",
        reclamation,
    )
    _envoyer_email(reclamation)
    return reclamation


def message_fosa(reclamation, auteur, texte, photos=None):
    """Message de la FOSA. Sur une réclamation résolue, il la rouvre : la FOSA
    signale que le problème n'est pas réglé."""
    texte = _texte_propre(texte)
    photos = _preparer_photos(photos)
    if not texte and not photos:
        raise ValueError("Le message est vide.")
    with transaction.atomic():
        reclamation = Reclamation.objects.select_for_update().get(pk=reclamation.pk)
        message = MessageReclamation.objects.create(
            reclamation=reclamation, auteur=auteur, de_la_fosa=True, texte=texte
        )
        _enregistrer_photos(reclamation, photos, message)
        rouverte = reclamation.est_close
        if rouverte:
            reclamation.statut = StatutReclamation.OUVERTE
            reclamation.date_resolution = None
        reclamation.non_lue_frps = True
        reclamation.date_activite = timezone.now()
        reclamation.save(update_fields=["statut", "date_resolution", "non_lue_frps", "date_activite"])

    _prevenir_personnel(
        f"Réclamation #{reclamation.pk}" + (" rouverte" if rouverte else " : nouveau message"),
        f"{reclamation.formation_sanitaire.nom} : {texte[:100] or 'photo jointe'}",
        reclamation,
    )
    # E-mail seulement à la réouverture : un simple message de suivi n'en vaut pas un,
    # le push et la pastille suffisent.
    if rouverte:
        _envoyer_email(reclamation, rouverte=True, message=message)
    return reclamation


def _envoyer_email(reclamation, rouverte=False, message=None):
    """Hors transaction et sans jamais lever : la réclamation est enregistrée, un
    relais SMTP en panne ne doit pas faire croire à la FOSA qu'elle ne l'est pas."""
    from notifications.emails import envoyer_email_reclamation

    try:
        envoyer_email_reclamation(reclamation, rouverte=rouverte, message=message)
    except Exception:  # noqa: BLE001
        logger.exception("Réclamation #%s : envoi des emails interrompu", reclamation.pk)


def reponse_frps(reclamation, auteur, texte="", statut=None, photos=None):
    """Réponse et/ou changement de statut par le personnel FRPS. La FOSA est prévenue
    par SMS quand la réclamation passe à « résolue »."""
    texte = _texte_propre(texte)
    photos = _preparer_photos(photos)
    if statut is not None and statut not in StatutReclamation.values:
        raise ValueError("Statut inconnu.")

    with transaction.atomic():
        reclamation = Reclamation.objects.select_for_update().get(pk=reclamation.pk)
        change_statut = statut is not None and statut != reclamation.statut
        if not texte and not photos and not change_statut:
            raise ValueError("Écrivez une réponse ou changez le statut.")
        champs = ["traitee_par", "date_activite"]
        if texte or photos:
            message = MessageReclamation.objects.create(
                reclamation=reclamation, auteur=auteur, de_la_fosa=False, texte=texte
            )
            _enregistrer_photos(reclamation, photos, message)
            reclamation.non_lue_fosa = True
            champs.append("non_lue_fosa")
        devient_resolue = change_statut and statut == StatutReclamation.RESOLUE
        if change_statut:
            reclamation.statut = statut
            reclamation.date_resolution = timezone.now() if devient_resolue else None
            reclamation.non_lue_fosa = True
            champs += ["statut", "date_resolution", "non_lue_fosa"]
        reclamation.traitee_par = auteur
        reclamation.date_activite = timezone.now()
        reclamation.save(update_fields=list(dict.fromkeys(champs)))

    _prevenir_fosa(reclamation, texte, devient_resolue)
    if devient_resolue:
        try:
            _sms_resolution(reclamation)
        except Exception:  # noqa: BLE001 - un SMS raté ne doit pas annuler la réponse
            logger.exception("Réclamation #%s : SMS de résolution non envoyé", reclamation.pk)
    return reclamation


def _prevenir_fosa(reclamation, texte, resolue):
    from notifications.push import envoyer_push_a_fosa

    titre = f"Réclamation #{reclamation.pk} " + ("résolue" if resolue else ": réponse du FRPS")
    corps = texte[:120] if texte else f"Statut : {reclamation.get_statut_display()}"
    try:
        envoyer_push_a_fosa(reclamation.formation_sanitaire, titre, corps, url=f"/reclamations/{reclamation.pk}/")
    except Exception:  # noqa: BLE001 - le push ne doit jamais faire échouer la réponse
        logger.exception("Réclamation #%s : push à la FOSA non envoyé", reclamation.pk)


def marquer_lue(reclamation, par_la_fosa):
    champ = "non_lue_fosa" if par_la_fosa else "non_lue_frps"
    if getattr(reclamation, champ):
        Reclamation.objects.filter(pk=reclamation.pk).update(**{champ: False})
        setattr(reclamation, champ, False)


def _prevenir_personnel(titre, corps, reclamation):
    """Push à tout le personnel FRPS actif, comme pour une nouvelle commande."""
    from accounts.models import Role, User
    from notifications.push import envoyer_push_aux_utilisateurs

    try:
        envoyer_push_aux_utilisateurs(
            User.objects.exclude(role=Role.FORMATION_SANITAIRE).filter(is_active=True),
            titre,
            corps,
            url=f"/reclamations/{reclamation.pk}/",
        )
    except Exception:  # noqa: BLE001 - le push ne doit jamais faire échouer la saisie
        logger.exception("Réclamation #%s : push non envoyé", reclamation.pk)


def _sms_resolution(reclamation):
    from notifications.models import TypeEvenement
    from notifications.services import _envoyer_a_destinataires, _sans_accents, numero_international

    fosa = reclamation.formation_sanitaire
    numero = fosa.telephone_contact or fosa.user.telephone
    if not numero:
        logger.warning("Réclamation #%s résolue : %s n'a aucun numéro", reclamation.pk, fosa.nom)
        return
    message = _sans_accents(
        f"FRPS-NO : votre reclamation #{reclamation.pk} ({reclamation.get_motif_display()}) est resolue. "
        "Detail dans l'application."
    )
    _envoyer_a_destinataires(
        [numero_international(numero)], message, TypeEvenement.RECLAMATION_RESOLUE, commande=reclamation.commande
    )
