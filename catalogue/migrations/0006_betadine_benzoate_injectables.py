"""Remet la Bétadine et le Benzoate de benzyle dans Injectables, à la demande du FRPS.

La migration 0005 les avait placés en Application externe ; le FRPS les veut en
Injectables, comme le Phénobarbital ampoule (déjà en Injectables).
"""

from django.db import migrations

CODES = ["POLYVI_4%_1000M///", "BENZOA_25%/_SC_12"]


def ranger_en_injectables(apps, schema_editor):
    Rayon = apps.get_model("catalogue", "Rayon")
    Produit = apps.get_model("catalogue", "Produit")

    injectables = Rayon.objects.filter(slug="injectables").first()
    if injectables is not None:
        Produit.objects.filter(code_sage__in=CODES).update(rayon=injectables)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0005_rayons_produits_sans_rayon"),
    ]

    operations = [
        migrations.RunPython(ranger_en_injectables, migrations.RunPython.noop),
    ]
