from django.core.management.base import BaseCommand

from accounts.models import FormationSanitaire, Role, User


class Command(BaseCommand):
    help = "Crée des comptes de démo : une formation sanitaire et du personnel FRPS (stock + comptabilité)."

    def handle(self, *args, **options):
        if not User.objects.filter(username="csi_bonamoussadi").exists():
            u = User.objects.create_user(
                username="csi_bonamoussadi",
                password="Formation2026!",
                role=Role.FORMATION_SANITAIRE,
                telephone="+237690000001",
            )
            FormationSanitaire.objects.create(
                user=u, nom="CSI Bonamoussadi", region="Littoral", district="Douala 5"
            )
            self.stdout.write(self.style.SUCCESS("Formation sanitaire créée : csi_bonamoussadi / Formation2026!"))

        if not User.objects.filter(username="stock_frps").exists():
            User.objects.create_user(
                username="stock_frps", password="Stock2026!", role=Role.PERSONNEL_STOCK, telephone="+237690000002"
            )
            self.stdout.write(self.style.SUCCESS("Personnel stock créé : stock_frps / Stock2026!"))

        if not User.objects.filter(username="compta_frps").exists():
            User.objects.create_user(
                username="compta_frps",
                password="Compta2026!",
                role=Role.PERSONNEL_COMPTABILITE,
                telephone="+237690000003",
            )
            self.stdout.write(self.style.SUCCESS("Personnel comptabilité créé : compta_frps / Compta2026!"))
