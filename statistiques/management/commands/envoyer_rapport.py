from django.core.management.base import BaseCommand

from statistiques.rapports import envoyer_rapport_periodique


class Command(BaseCommand):
    """Envoie le rapport d'activité périodique par email aux comptes admin actifs
    (voir statistiques/rapports.py). Pensé pour être déclenché régulièrement par un
    planificateur externe (ex: Render Cron Job) — cette commande ne se replanifie pas
    elle-même.

    En local, EMAIL_BACKEND_MODE=console (valeur par défaut) affiche l'email dans le
    terminal au lieu de l'envoyer réellement — pratique pour vérifier le contenu sans
    consommer de quota SMTP."""

    help = "Envoie le rapport d'activité périodique par email"

    def add_arguments(self, parser):
        parser.add_argument("--jours", type=int, default=7, help="Nombre de jours couverts par le rapport (défaut: 7)")
        parser.add_argument(
            "--destinataire", action="append", default=None,
            help="Email destinataire (répétable). Par défaut : comptes admin actifs avec email."
        )

    def handle(self, *args, **options):
        nb, sujet, corps = envoyer_rapport_periodique(jours=options["jours"], destinataires=options["destinataire"])
        if nb == 0:
            self.stderr.write(self.style.WARNING(
                "Aucun destinataire : aucun compte admin actif n'a d'email renseigné (et --destinataire non fourni)."
            ))
            return
        self.stdout.write(self.style.SUCCESS(f"Rapport envoyé à {nb} destinataire(s) : {sujet}"))
