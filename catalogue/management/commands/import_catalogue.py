import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand

from catalogue.models import Magasin, Produit

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "produits_magasin_principal.csv"

TWO_PLACES = Decimal("0.01")


def _decimal(valeur):
    try:
        return Decimal(valeur.strip()).quantize(TWO_PLACES)
    except (InvalidOperation, AttributeError):
        return Decimal("0.00")


class Command(BaseCommand):
    """Importe/actualise le catalogue depuis catalogue/data/produits_magasin_principal.csv
    (export Sage du magasin Principal, colonnes code_sage;nom;unite;prix_unitaire;stock_disponible).
    Idempotent : à relancer sans risque après un nouvel export Sage.
    """

    help = "Importe le catalogue depuis catalogue/data/produits_magasin_principal.csv"

    def handle(self, *args, **options):
        crees = 0
        maj = 0
        ignores = 0

        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter=";")
            next(reader)  # en-tête
            for row in reader:
                if len(row) < 5:
                    ignores += 1
                    continue

                code_sage = row[0].strip()
                # Une ligne (nom contenant un ';') peut avoir plus de 5 colonnes :
                # on prend les 3 dernières comme unite/prix/stock, le reste comme nom.
                stock_disponible = row[-1]
                prix_unitaire = row[-2]
                unite = row[-3].strip()
                nom = ";".join(row[1:-3]).strip()

                if not code_sage or not nom:
                    ignores += 1
                    continue

                _, created = Produit.objects.update_or_create(
                    code_sage=code_sage,
                    defaults={
                        "nom": nom,
                        "unite": unite,
                        "prix_unitaire": _decimal(prix_unitaire),
                        "stock_disponible": int(_decimal(stock_disponible)),
                        "magasin": Magasin.PRINCIPAL,
                    },
                )
                crees += int(created)
                maj += int(not created)

        self.stdout.write(
            self.style.SUCCESS(f"{crees} produits créés, {maj} mis à jour, {ignores} lignes ignorées.")
        )
