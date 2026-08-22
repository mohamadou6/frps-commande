import csv
from pathlib import Path

from django.db import migrations

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "rayons_classification.csv"

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


def importer_rayons(apps, schema_editor):
    Rayon = apps.get_model("catalogue", "Rayon")
    Produit = apps.get_model("catalogue", "Produit")

    rayons_par_slug = {}
    for slug, nom, icone, ordre in RAYONS:
        rayon, _ = Rayon.objects.update_or_create(slug=slug, defaults={"nom": nom, "icone": icone, "ordre": ordre})
        rayons_par_slug[slug] = rayon

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            code_sage = row["code_sage"].strip()
            rayon = rayons_par_slug.get(row["rayon"].strip())
            if rayon is not None:
                Produit.objects.filter(code_sage=code_sage).update(rayon=rayon)


def revenir_en_arriere(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0003_rayon_produit_rayon"),
    ]

    operations = [
        migrations.RunPython(importer_rayons, revenir_en_arriere),
    ]
