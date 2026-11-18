"""Paramétrage des destinataires e-mail par l'admin FRPS (page Paramètres)."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import ENVOIS_PARAMETRABLES, DestinataireEmail

CHAMPS_ENVOIS = [champ for champ, _libelle, _aide in ENVOIS_PARAMETRABLES]


def _normaliser_email(email):
    email = (email or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise ValueError(f"« {email or '(vide)'} » n'est pas une adresse e-mail valide.")
    return email


def ajouter_destinataire(email, nom="", envois=()):
    email = _normaliser_email(email)
    envois = [champ for champ in envois if champ in CHAMPS_ENVOIS]
    if not envois:
        raise ValueError("Cochez au moins un envoi pour cette adresse.")
    if DestinataireEmail.objects.filter(email=email).exists():
        raise ValueError(f"{email} est déjà dans la liste.")
    return DestinataireEmail.objects.create(
        email=email,
        nom=(nom or "").strip()[:100],
        **{champ: champ in envois for champ in CHAMPS_ENVOIS},
    )


def modifier_destinataire(destinataire, actif, envois):
    """Enregistre les cases cochées d'une ligne. Une adresse sans aucun envoi coché ne
    servirait à rien : on demande plutôt de la désactiver ou de la supprimer."""
    envois = [champ for champ in envois if champ in CHAMPS_ENVOIS]
    if not envois:
        raise ValueError(f"{destinataire.email} : cochez au moins un envoi, ou supprimez l'adresse.")
    destinataire.actif = bool(actif)
    for champ in CHAMPS_ENVOIS:
        setattr(destinataire, champ, champ in envois)
    destinataire.save(update_fields=["actif", *CHAMPS_ENVOIS])
    return destinataire
