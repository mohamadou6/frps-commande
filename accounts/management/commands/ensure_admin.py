import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Crée le compte admin FRPS s'il n'existe pas encore, à partir des variables
    d'environnement DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_EMAIL /
    DJANGO_SUPERUSER_PASSWORD. Ne fait rien si les variables ne sont pas définies,
    ou si le compte existe déjà (idempotent, safe à lancer à chaque déploiement).
    """

    help = "Crée le superutilisateur admin FRPS depuis les variables d'environnement, si absent."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD absents : rien à faire.")
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Compte admin '{username}' déjà présent.")
            return

        User.objects.create_superuser(username=username, email=email, password=password, role="admin")
        self.stdout.write(self.style.SUCCESS(f"Compte admin '{username}' créé."))
