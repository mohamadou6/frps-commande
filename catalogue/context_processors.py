from .services import nombre_promotions


def offres(request):
    """Nombre de promotions (offres spéciales + prix en baisse), pour la pastille du menu des FOSA. `fiche_fosa`
    et non `user.formation_sanitaire` : un compte FOSA sans fiche ferait tout tomber en 500."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_formation_sanitaire or user.fiche_fosa is None:
        return {}
    return {"nb_promotions_menu": nombre_promotions()}
