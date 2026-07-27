import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand

from catalogue.models import Produit

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
REF_CSV = DATA_DIR / "produits_magasin_principal.csv"
UPDATE_CSV = DATA_DIR / "stock_actualise_2026-07-27.csv"

TWO_PLACES = Decimal("0.01")


def _decimal(valeur):
    try:
        return Decimal(valeur.strip()).quantize(TWO_PLACES)
    except (InvalidOperation, AttributeError):
        return Decimal("0.00")


def _read_updates_with_code_sage(path):
    """Fichier avec code_sage (colonnes code_sage;nom;...;prix_unitaire;stock_disponible,
    éventuellement plus de colonnes si le nom contient un ';' — mêmes conventions que
    import_catalogue.py). Association directe et fiable par code_sage."""
    updates = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        for row in reader:
            while row and row[-1] == "":
                row.pop()
            if len(row) < 4:
                continue
            code_sage = row[0].strip()
            stock = row[-1]
            prix = row[-2]
            if not code_sage:
                continue
            updates[code_sage] = (_decimal(prix), int(_decimal(stock)))
    return updates


def _read_updates_by_position(update_csv):
    """Fichier sans code_sage (colonnes nom;prix_unitaire;stock_disponible). Le nom seul
    n'est pas fiable pour l'association (encodage abîmé dans le fichier de référence et
    doublons de noms dans le catalogue) : on associe donc par position, ligne à ligne,
    avec le code_sage situé à la même position dans produits_magasin_principal.csv."""
    code_sages = []
    with open(REF_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        for row in reader:
            if len(row) < 5:
                continue
            code_sages.append(row[0].strip())

    valeurs = []
    with open(update_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        for row in reader:
            valeurs.append((_decimal(row[1]), int(_decimal(row[2]))))

    if len(code_sages) != len(valeurs):
        raise ValueError(f"Nombre de lignes différent : {len(code_sages)} vs {len(valeurs)}")

    return dict(zip(code_sages, valeurs))


class Command(BaseCommand):
    """Met à jour prix_unitaire/stock_disponible depuis un fichier CSV fourni par
    l'utilisateur (export Sage corrigé). Ne crée aucun produit, ne touche ni au nom,
    ni à l'unité, ni au magasin — seulement prix_unitaire/stock_disponible.

    Deux formats acceptés :
    - avec --file : CSV avec code_sage en 1ère colonne (association directe, fiable)
    - sans --file : ancien format sans code_sage (stock_actualise_2026-07-27.csv),
      association par position avec produits_magasin_principal.csv (voir
      _read_updates_by_position)
    """

    help = "Met à jour prix_unitaire/stock_disponible depuis un fichier CSV d'actualisation"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche seulement les changements")
        parser.add_argument("--file", help="Chemin du CSV avec code_sage (association directe)")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if options["file"]:
            updates = _read_updates_with_code_sage(Path(options["file"]))
        else:
            try:
                updates = _read_updates_by_position(UPDATE_CSV)
            except ValueError as exc:
                self.stderr.write(self.style.ERROR(f"{exc} — abandon."))
                return

        produits = {p.code_sage: p for p in Produit.objects.filter(code_sage__in=updates.keys())}

        introuvables = 0
        inchanges = 0
        a_modifier = []
        for code_sage, (prix, stock) in updates.items():
            produit = produits.get(code_sage)
            if produit is None:
                introuvables += 1
                continue
            if produit.prix_unitaire == prix and produit.stock_disponible == stock:
                inchanges += 1
                continue
            if dry_run:
                self.stdout.write(
                    f"{code_sage} ({produit.nom}) : prix {produit.prix_unitaire}->{prix}, "
                    f"stock {produit.stock_disponible}->{stock}"
                )
            produit.prix_unitaire = prix
            produit.stock_disponible = stock
            a_modifier.append(produit)

        if not dry_run and a_modifier:
            Produit.objects.bulk_update(a_modifier, ["prix_unitaire", "stock_disponible"], batch_size=200)

        verbe = "à modifier (dry-run)" if dry_run else "modifiés"
        self.stdout.write(self.style.SUCCESS(
            f"{len(a_modifier)} produits {verbe}, {inchanges} inchangés, {introuvables} introuvables."
        ))
