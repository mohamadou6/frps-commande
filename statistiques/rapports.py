from datetime import date, timedelta

from django.conf import settings
from django.core.mail import send_mail

from accounts.models import Role, User

from .services import donnees_tableau_de_bord


def _formatter_rapport_texte(donnees):
    lignes = [
        f"Rapport d'activité Commande FRPS — du {donnees['debut']} au {donnees['fin']}",
        "=" * 60,
        "",
        f"Commandes sur la période : {donnees['nb_commandes_periode']}",
        f"Montant total : {donnees['montant_periode']} FCFA",
        f"Formations sanitaires actives : {donnees['nb_fosa_actives']}",
        f"Produits en rupture : {donnees['nb_rupture']}",
        f"Produits menacés de rupture : {donnees['nb_menace']}",
        "",
    ]

    lignes.append(f"Formations sanitaires actives n'ayant jamais commandé : {donnees['nb_fosa_sans_commande']}")
    if donnees["fosa_sans_commande"]:
        for fosa in donnees["fosa_sans_commande"]:
            lignes.append(f"  - {fosa.nom} ({fosa.district})")
    lignes.append("")

    lignes.append("Produits les plus commandés sur la période :")
    if donnees["top_produits_periode"]:
        for ligne in donnees["top_produits_periode"]:
            lignes.append(f"  - {ligne['produit__nom']} : {ligne['quantite']}")
    else:
        lignes.append("  (aucune commande sur cette période)")
    lignes.append("")

    lignes.append("Dernières commandes :")
    if donnees["dernieres_commandes"]:
        for commande in donnees["dernieres_commandes"]:
            date_str = commande.date_confirmation.strftime("%d/%m/%Y %H:%M") if commande.date_confirmation else "-"
            lignes.append(
                f"  - #{commande.pk} {commande.formation_sanitaire.nom} — {date_str} — {commande.montant_total} FCFA"
            )
    else:
        lignes.append("  (aucune commande sur cette période)")

    lignes.append("")
    lignes.append("--")
    lignes.append("Rapport généré automatiquement par Commande FRPS.")

    return "\n".join(lignes)


def destinataires_rapport():
    """Comptes admin actifs avec un email renseigné. Reproduit le même filtre que
    les notifications SMS (voir notifications/services.py) : l'admin supervise tout."""
    return list(
        User.objects.filter(role=Role.ADMIN, is_active=True).exclude(email="").values_list("email", flat=True)
    )


def envoyer_rapport_periodique(jours=7, destinataires=None):
    """Génère et envoie le rapport d'activité des `jours` derniers jours aux
    destinataires donnés (par défaut : les comptes admin actifs avec email).
    Retourne (nb_destinataires, sujet, corps) — utile pour les tests/la commande CLI."""
    aujourd_hui = date.today()
    debut = str(aujourd_hui - timedelta(days=jours))
    fin = str(aujourd_hui)

    donnees = donnees_tableau_de_bord(debut, fin)
    corps = _formatter_rapport_texte(donnees)
    sujet = f"[Commande FRPS] Rapport d'activité du {debut} au {fin}"

    destinataires = destinataires if destinataires is not None else destinataires_rapport()
    if destinataires:
        send_mail(
            subject=sujet,
            message=corps,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=destinataires,
            fail_silently=False,
        )

    return len(destinataires), sujet, corps
