import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from accounts.models import FormationSanitaire, Role, User

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fosa_nord.csv"


class Command(BaseCommand):
    """Importe le référentiel des formations sanitaires (région/district/nom) depuis
    accounts/data/fosa_nord.csv.

    Crée pour chaque FOSA absente de la base un compte utilisateur désactivé
    (role=formation_sanitaire, sans mot de passe utilisable) : l'admin FRPS
    l'active et lui donne un mot de passe quand la formation sanitaire commence
    réellement à utiliser l'appli (voir /admin/accounts/user/). Idempotent :
    ignore les FOSA déjà présentes (même nom + district)."""

    help = "Importe le référentiel FOSA depuis accounts/data/fosa_nord.csv"

    def handle(self, *args, **options):
        crees = 0
        ignores = 0
        usernames_utilises = set(User.objects.values_list("username", flat=True))

        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                region = (row.get("region") or "").strip()
                district = (row.get("district") or "").strip()
                nom = (row.get("nom") or "").strip()
                if not nom:
                    continue

                if FormationSanitaire.objects.filter(nom=nom, district=district).exists():
                    ignores += 1
                    continue

                username = self._username_unique(nom, usernames_utilises)
                usernames_utilises.add(username)

                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        password=None,
                        role=Role.FORMATION_SANITAIRE,
                        is_active=False,
                    )
                    FormationSanitaire.objects.create(
                        user=user, nom=nom, region=region, district=district
                    )
                crees += 1

        self.stdout.write(
            self.style.SUCCESS(f"{crees} formations sanitaires créées, {ignores} déjà présentes.")
        )

    @staticmethod
    def _username_unique(nom, deja_utilises):
        base = slugify(nom)[:140] or "fosa"
        username = base
        i = 2
        while username in deja_utilises:
            username = f"{base}-{i}"
            i += 1
        return username
