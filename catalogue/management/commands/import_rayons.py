import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from catalogue.models import Produit, Rayon

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rayons_classification.csv"

# (slug, nom affiché, icône, ordre d'affichage)
RAYONS = [
    ("injectables", "Injectables", "💉", 1),
    ("comprimes", "Comprimés", "💊", 2),
    ("sirops", "Sirops", "🧴", 3),
    ("solutes", "Solutés & perfusions", "💧", 4),
    ("consommables-medicaux", "Consommables médicaux", "🩹", 5),
    ("sante-de-reproduction", "Santé de la reproduction", "🤰", 6),
    ("kits", "Kits", "🧰", 7),
    ("papeterie-et-froid", "Papeterie et chaîne du froid", "📋", 8),
]


class Command(BaseCommand):
    """Crée/actualise les rayons puis rattache les produits selon
    catalogue/data/rayons_classification.csv (colonnes code_sage;rayon).
    Idempotent : à relancer sans risque après un nouvel export de classification.
    """

    help = "Crée les rayons et rattache les produits depuis catalogue/data/rayons_classification.csv"

    def handle(self, *args, **options):
        rayons_par_slug = {}
        for slug, nom, icone, ordre in RAYONS:
            rayon, _ = Rayon.objects.update_or_create(
                slug=slug, defaults={"nom": nom, "icone": icone, "ordre": ordre}
            )
            rayons_par_slug[slug] = rayon

        maj = 0
        introuvables = []

        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                code_sage = row["code_sage"].strip()
                slug = row["rayon"].strip()
                rayon = rayons_par_slug.get(slug)
                if rayon is None:
                    self.stderr.write(f"Rayon inconnu '{slug}' pour {code_sage}, ignoré.")
                    continue
                nb = Produit.objects.filter(code_sage=code_sage).update(rayon=rayon)
                if nb:
                    maj += nb
                else:
                    introuvables.append(code_sage)

        self.stdout.write(self.style.SUCCESS(f"{len(rayons_par_slug)} rayons synchronisés, {maj} produits rattachés."))
        if introuvables:
            self.stdout.write(self.style.WARNING(
                f"{len(introuvables)} codes du fichier de classification introuvables en base : "
                + ", ".join(introuvables)
            ))
