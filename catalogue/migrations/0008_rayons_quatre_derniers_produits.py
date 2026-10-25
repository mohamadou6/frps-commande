"""Range les 4 derniers produits sans rayon, absents du fichier du 25/10/2026.

Tous les quatre sont à stock et prix nuls : invisibles aujourd'hui, ils seraient
apparus sans rayon dès la saisie de leur stock. Rayons déduits du nom du produit,
proposition acceptée le 25/10/2026 ; à corriger dans l'admin si le FRPS en décide autrement.

Comme pour 0007, un rayon déjà choisi (à la main dans l'admin) n'est jamais écrasé.
"""

from django.db import migrations

CLASSEMENT = {
    "COPOVA_///////_CU": "laboratoire",  # Corps de pompes Vacutainer (prélèvement sanguin)
    "AEDHOO_//////////": "materiel",  # EAD Hook (Green)
    "LIDNAP_5%//_SO_OR": "application-externe",  # Lidocaïne à la Naphtazoline 5 % solution
    "TOTAMI_////_//_//": "solutes",  # Totamine concentré
}


def classer(apps, schema_editor):
    Rayon = apps.get_model("catalogue", "Rayon")
    Produit = apps.get_model("catalogue", "Produit")

    rayons = {r.slug: r for r in Rayon.objects.filter(slug__in=set(CLASSEMENT.values()))}
    for code_sage, slug in CLASSEMENT.items():
        rayon = rayons.get(slug)
        if rayon is not None:
            Produit.objects.filter(code_sage=code_sage, rayon__isnull=True).update(rayon=rayon)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0007_rayons_laboratoire_materiel_et_classement"),
    ]

    operations = [
        migrations.RunPython(classer, migrations.RunPython.noop),
    ]
