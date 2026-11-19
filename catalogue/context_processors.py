import logging

from django.contrib import messages

from .services import nombre_promotions

logger = logging.getLogger(__name__)


def offres(request):
    """Pour les FOSA, sur toutes les pages : nombre de promotions (pastille du menu)
    et préparation de la commande mensuelle programmée quand son jour est atteint.

    La préparation est faite ici faute de tâche planifiée sur l'hébergement : la
    FOSA trouve son panier prêt dès sa première visite après le jour choisi. Une
    seule fois par mois (catalogue/espace_fosa.py preparer_si_echue).

    `fiche_fosa` et non `user.formation_sanitaire` : un compte FOSA sans fiche ferait
    tout tomber en 500."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_formation_sanitaire:
        return {}
    fosa = user.fiche_fosa
    if fosa is None:
        return {}

    _preparer_commande_mensuelle(request, fosa)
    return {"nb_promotions_menu": nombre_promotions()}


def _preparer_commande_mensuelle(request, fosa):
    from .espace_fosa import preparer_si_echue

    try:
        resultat = preparer_si_echue(fosa)
    except Exception:  # noqa: BLE001 - jamais une page en erreur pour cette commodité
        logger.exception("Commande mensuelle de %s non préparée", fosa.nom)
        return
    if resultat is None:
        return
    ajoutes, reduits, indisponibles = resultat
    nb = len(ajoutes) + len(reduits)
    if not nb:
        messages.warning(request, "Commande du mois : aucun de vos produits habituels n'est disponible aujourd'hui.")
        return
    messages.success(
        request,
        f"📅 Votre commande du mois est prête : {nb} produit(s) habituel(s) au panier. Vérifiez puis validez.",
    )
    if indisponibles:
        messages.warning(request, "Indisponible(s) ce mois-ci : " + ", ".join(indisponibles) + ".")
