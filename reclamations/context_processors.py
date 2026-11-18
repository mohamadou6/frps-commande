from .models import Reclamation


def reclamations_non_lues(request):
    """Pastille du menu Réclamations, sur toutes les pages. `fiche_fosa` et non
    `user.formation_sanitaire` : un compte FOSA sans fiche ferait tout tomber en 500."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    if user.is_formation_sanitaire:
        fiche = user.fiche_fosa
        if fiche is None:
            return {}
        compte = Reclamation.objects.filter(formation_sanitaire=fiche, non_lue_fosa=True).count()
    else:
        compte = Reclamation.objects.filter(non_lue_frps=True).count()
    return {"reclamations_non_lues_count": compte}
