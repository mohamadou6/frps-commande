"""Range les produits restés sans rayon et crée les rayons Laboratoire et Matériel.

Source : catalogue/data/rayons_2026-10-25.csv (1 059 produits). Colonne « source » :
- « fichier FRPS » : rayon donné par le FRPS (fichier du 25/10/2026, 236 produits) ;
- « proposition » : rayon déduit du nom du produit, selon les conventions de ce fichier
  (823 produits absents du fichier FRPS).

Seuls les produits encore sans rayon sont touchés : un classement déjà fait, à la main
ou par une migration précédente, n'est jamais écrasé.
"""

import csv
from pathlib import Path

from django.db import migrations

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "rayons_2026-10-25.csv"

NOUVEAUX_RAYONS = [
    ("laboratoire", "Laboratoire", "🧪", 10),
    ("materiel", "Matériel", "🩺", 11),
]


def classer(apps, schema_editor):
    Rayon = apps.get_model("catalogue", "Rayon")
    Produit = apps.get_model("catalogue", "Produit")

    for slug, nom, icone, ordre in NOUVEAUX_RAYONS:
        Rayon.objects.get_or_create(slug=slug, defaults={"nom": nom, "icone": icone, "ordre": ordre})
    rayons = {r.slug: r for r in Rayon.objects.all()}

    codes_par_rayon = {}
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for ligne in csv.DictReader(f, delimiter=";"):
            codes_par_rayon.setdefault(ligne["rayon"].strip(), []).append(ligne["code_sage"].strip())

    for slug, codes in codes_par_rayon.items():
        rayon = rayons.get(slug)
        if rayon is not None:
            Produit.objects.filter(code_sage__in=codes, rayon__isnull=True).update(rayon=rayon)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0006_betadine_benzoate_injectables"),
    ]

    operations = [
        migrations.RunPython(classer, migrations.RunPython.noop),
    ]
