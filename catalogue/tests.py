import importlib
import io
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import Role, User

from .models import Produit, Rayon


def _classeur(lignes):
    wb = Workbook()
    ws = wb.active
    ws.append(["code_sage", "prix_unitaire", "stock_disponible"])
    for ligne in lignes:
        ws.append(list(ligne))
    contenu = io.BytesIO()
    wb.save(contenu)
    return SimpleUploadedFile("produits.xlsx", contenu.getvalue())


class ImportVariationDePrixTests(TestCase):
    """L'import signale en couleur chaque prix qui monte ou qui baisse."""

    def setUp(self):
        admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        self.client.force_login(admin)
        for code, prix in (("HAUSSE", "100"), ("BAISSE", "100"), ("STOCK", "100")):
            Produit.objects.create(code_sage=code, nom=code, prix_unitaire=Decimal(prix), stock_disponible=10)

    def _importer(self):
        fichier = _classeur([("STOCK", 100, 5), ("HAUSSE", 120, 10), ("BAISSE", 80.5, 10)])
        return self.client.post(reverse("catalogue:importer"), {"fichier": fichier})

    def test_chaque_ligne_porte_le_sens_de_variation_du_prix(self):
        resultats = self._importer().context["resultats"]
        variations = {m["code_sage"]: m["variation_prix"] for m in resultats["modifies"]}

        self.assertEqual(variations, {"HAUSSE": "hausse", "BAISSE": "baisse", "STOCK": ""})
        self.assertEqual((resultats["nb_hausses"], resultats["nb_baisses"]), (1, 1))

    def test_les_changements_de_prix_passent_en_tete(self):
        resultats = self._importer().context["resultats"]

        self.assertEqual(resultats["modifies"][-1]["code_sage"], "STOCK")

    def test_la_page_colore_hausse_et_baisse(self):
        reponse = self._importer()

        self.assertContains(reponse, 'class="prix-hausse"')
        self.assertContains(reponse, 'class="prix-baisse"')


class MigrationRayonsProduitsSansRayonTests(TestCase):
    def setUp(self):
        self.migration = importlib.import_module("catalogue.migrations.0005_rayons_produits_sans_rayon")

    def test_range_les_produits_sans_rayon_et_cree_application_externe(self):
        Produit.objects.create(code_sage="DICLO_30G///", nom="Diclofenac crème", prix_unitaire=1, stock_disponible=1)
        Produit.objects.create(code_sage="CAPTO_25MG", nom="Captopril", prix_unitaire=1, stock_disponible=1)

        self.migration.classer(django_apps, None)

        self.assertEqual(Produit.objects.get(code_sage="DICLO_30G///").rayon.slug, "application-externe")
        self.assertEqual(Produit.objects.get(code_sage="CAPTO_25MG").rayon.slug, "comprimes")

    def test_n_ecrase_pas_un_rayon_deja_choisi_a_la_main(self):
        sirops = Rayon.objects.get(slug="sirops")
        Produit.objects.create(
            code_sage="CAPTO_25MG", nom="Captopril", prix_unitaire=1, stock_disponible=1, rayon=sirops
        )

        self.migration.classer(django_apps, None)

        self.assertEqual(Produit.objects.get(code_sage="CAPTO_25MG").rayon, sirops)

    def test_les_trois_corrections_validees_par_le_frps(self):
        rayon_de = {c: r for r, liste in self.migration.CLASSEMENT.items() for c in liste}

        self.assertEqual(rayon_de["PHENOB_100/_AM_IV"], "injectables")
        self.assertEqual(rayon_de["POLYVI_4%_1000M///"], "application-externe")
        self.assertEqual(rayon_de["BENZOA_25%/_SC_12"], "application-externe")

    def test_le_classement_couvre_les_60_produits_du_fichier_sans_doublon(self):
        codes = [c for liste in self.migration.CLASSEMENT.values() for c in liste]

        self.assertEqual(len(codes), 60)
        self.assertEqual(len(set(codes)), 60)
