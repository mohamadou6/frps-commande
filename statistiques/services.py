from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

from accounts.models import FormationSanitaire
from catalogue.models import Magasin, Produit
from commandes.models import Commande, LigneCommande, StatutCommande

COMMANDES_EFFECTIVES = [StatutCommande.CONFIRMEE, StatutCommande.PAYEE]


def donnees_tableau_de_bord(debut, fin):
    """Rassemble les indicateurs du tableau de bord (statistiques:index) pour une
    période donnée. Utilisé à la fois par la vue web et par le rapport par email
    (statistiques/rapports.py), pour ne pas dupliquer les requêtes."""
    commandes_periode = Commande.objects.filter(
        statut__in=COMMANDES_EFFECTIVES,
        date_confirmation__date__gte=debut,
        date_confirmation__date__lte=fin,
    )
    nb_commandes_periode = commandes_periode.count()
    montant_periode = commandes_periode.aggregate(total=Sum("montant_total"))["total"] or 0

    produits_catalogue = Produit.objects.filter(magasin__in=[Magasin.PRINCIPAL, Magasin.UCPC])
    nb_rupture = produits_catalogue.filter(stock_disponible=0).count()
    nb_menace = (
        LigneCommande.objects.filter(
            produit__in=produits_catalogue.filter(stock_disponible__gt=0),
            commande__statut__in=COMMANDES_EFFECTIVES,
            commande__date_confirmation__date__gte=debut,
            commande__date_confirmation__date__lte=fin,
        )
        .values("produit_id", "produit__stock_disponible")
        .annotate(quantite=Sum("quantite"))
        .filter(quantite__gte=F("produit__stock_disponible"))
        .count()
    )

    fosa_actives = FormationSanitaire.objects.filter(user__is_active=True)
    nb_fosa_actives = fosa_actives.count()
    fosa_sans_commande = fosa_actives.exclude(commandes__statut__in=COMMANDES_EFFECTIVES).order_by("nom")
    nb_fosa_sans_commande = fosa_sans_commande.count()

    dernieres_commandes = (
        commandes_periode.select_related("formation_sanitaire").order_by("-date_confirmation")[:10]
    )

    top_produits_periode = (
        LigneCommande.objects.filter(
            commande__statut__in=COMMANDES_EFFECTIVES,
            commande__date_confirmation__date__gte=debut,
            commande__date_confirmation__date__lte=fin,
        )
        .values("produit__nom")
        .annotate(quantite=Sum("quantite"))
        .order_by("-quantite")[:5]
    )

    return {
        "debut": debut,
        "fin": fin,
        "nb_commandes_periode": nb_commandes_periode,
        "montant_periode": montant_periode,
        "nb_rupture": nb_rupture,
        "nb_menace": nb_menace,
        "nb_fosa_actives": nb_fosa_actives,
        "nb_fosa_sans_commande": nb_fosa_sans_commande,
        "fosa_sans_commande": list(fosa_sans_commande[:10]),
        "dernieres_commandes": list(dernieres_commandes),
        "top_produits_periode": list(top_produits_periode),
    }
