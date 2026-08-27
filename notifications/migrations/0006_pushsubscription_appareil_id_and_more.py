import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_pushsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushsubscription",
            name="appareil_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Identifiant stable du navigateur/appareil (tiré du localStorage). Sert à "
                    "remplacer l'abonnement précédent du même appareil au lieu d'en accumuler un de plus."
                ),
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="pushsubscription",
            name="date_confirmation",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                help_text=(
                    "Dernier réenregistrement par l'appareil : au-delà de la péremption, "
                    "l'abonnement est supprimé."
                ),
            ),
            preserve_default=False,
        ),
    ]
