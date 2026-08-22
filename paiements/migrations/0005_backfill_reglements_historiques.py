from django.db import migrations


def backfill_reglements_historiques(apps, schema_editor):
    """Les paiements saisis avant l'introduction de ReglementPaiement n'ont pas
    d'historique de versements : on cree une ligne unique reprenant le montant
    deja enregistre, pour que le total affiche corresponde toujours a la somme
    de l'historique."""
    Paiement = apps.get_model("paiements", "Paiement")
    ReglementPaiement = apps.get_model("paiements", "ReglementPaiement")

    for paiement in Paiement.objects.filter(montant_paye__gt=0):
        if not ReglementPaiement.objects.filter(paiement=paiement).exists():
            ReglementPaiement.objects.create(
                paiement=paiement,
                montant=paiement.montant_paye,
                methode=paiement.methode,
                saisi_par=paiement.maj_par,
            )


def revenir_en_arriere(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("paiements", "0004_alter_paiement_methode_reglementpaiement"),
    ]

    operations = [
        migrations.RunPython(backfill_reglements_historiques, revenir_en_arriere),
    ]
