from .models import Commande, StatutCommande


def panier_resume(request):
    """Nombre de lignes du panier en cours, pour le badge de la navbar : sans lui,
    il fallait quitter le catalogue et ouvrir le panier pour savoir où on en était.

    On lit le brouillon existant sans passer par services.get_panier(), qui en
    créerait un à chaque page vue par une FOSA."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_formation_sanitaire:
        return {}

    panier = Commande.objects.filter(
        formation_sanitaire=user.formation_sanitaire, statut=StatutCommande.BROUILLON
    ).first()
    return {"panier_nb_lignes": panier.lignes.count() if panier else 0}
