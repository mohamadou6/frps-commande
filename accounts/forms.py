from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

MESSAGE_FOSA_SANS_FICHE = (
    "Ce compte n'est rattaché à aucune formation sanitaire. "
    "Contactez la FRPS pour qu'elle complète votre compte."
)


class ConnexionForm(AuthenticationForm):
    """Refuse la connexion d'un compte FOSA sans fiche FormationSanitaire : connecté,
    il ne pouvait rien faire d'autre qu'obtenir des erreurs 500. Le drapeau
    `compte_non_rattache` permet au gabarit d'afficher ce motif plutôt que
    « Identifiants incorrects », qui aurait fait chercher une faute de mot de passe."""

    compte_non_rattache = False

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.est_fosa_sans_fiche:
            self.compte_non_rattache = True
            raise ValidationError(MESSAGE_FOSA_SANS_FICHE, code="fosa_sans_fiche")
