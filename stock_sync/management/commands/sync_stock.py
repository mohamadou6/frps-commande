from django.core.management.base import BaseCommand
from django.db import transaction

from catalogue.models import Produit
from stock_sync.connectors import get_stock_connector


class Command(BaseCommand):
    help = "Synchronise le catalogue local depuis la source de stock (SQL Server FRPS ou mock)."

    @transaction.atomic
    def handle(self, *args, **options):
        connector = get_stock_connector()
        produits_distants = connector.fetch_produits()
        codes_vus = set()

        for data in produits_distants:
            code_sage = data["code_sage"]
            codes_vus.add(code_sage)
            Produit.objects.update_or_create(
                code_sage=code_sage,
                defaults={
                    "nom": data["nom"],
                    "unite": data.get("unite", ""),
                    "prix_unitaire": data["prix_unitaire"],
                    "stock_disponible": data["stock_disponible"],
                    "actif": True,
                },
            )

        desactives = Produit.objects.exclude(code_sage__in=codes_vus).update(actif=False)

        self.stdout.write(self.style.SUCCESS(
            f"Synchro terminée : {len(codes_vus)} produits mis à jour, {desactives} désactivés (absents de la source)."
        ))
