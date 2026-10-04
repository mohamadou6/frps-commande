from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations


def _arrondir(valeur):
    return valeur.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def arrondir_montants_totaux(apps, schema_editor):
    """Les commandes passees avant l'arrondi du total a l'enregistrement gardent un
    total a decimales (ex. 1 718,10) alors que l'ecran affichait 1 718 : le solde
    ne tombait jamais a zero. On les aligne sur la regle desormais appliquee par
    Commande.recalculer_montant.

    Les reglements deja saisis ne sont PAS modifies : ce sont des sommes recues,
    pas des totaux calcules. Un eventuel ecart de centimes est absorbe par
    Commande.solde_restant."""
    Commande = apps.get_model("commandes", "Commande")
    Paiement = apps.get_model("paiements", "Paiement")

    commandes_modifiees = 0
    for commande in Commande.objects.only("pk", "montant_total").iterator():
        arrondi = _arrondir(commande.montant_total)
        if arrondi != commande.montant_total:
            Commande.objects.filter(pk=commande.pk).update(montant_total=arrondi)
            commandes_modifiees += 1

    # Paiement.montant est la copie du total de la commande prise a la creation du paiement.
    for paiement in Paiement.objects.only("pk", "montant").iterator():
        arrondi = _arrondir(paiement.montant)
        if arrondi != paiement.montant:
            Paiement.objects.filter(pk=paiement.pk).update(montant=arrondi)

    if commandes_modifiees:
        print(f" {commandes_modifiees} commande(s) au total arrondi au FCFA", end="")


class Migration(migrations.Migration):
    dependencies = [
        ("commandes", "0001_initial"),
        ("paiements", "0006_alter_reglementpaiement_options_and_more"),
    ]

    operations = [
        # Rien a defaire au retour arriere : le total exact reste recalculable a tout
        # moment depuis les lignes (prix_unitaire_snapshot x quantite).
        migrations.RunPython(arrondir_montants_totaux, migrations.RunPython.noop),
    ]
