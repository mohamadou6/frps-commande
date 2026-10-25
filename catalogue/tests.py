import csv
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

    def test_phenobarbital_betadine_et_benzoate_finissent_en_injectables(self):
        codes = ["PHENOB_100/_AM_IV", "POLYVI_4%_1000M///", "BENZOA_25%/_SC_12"]
        for code in codes:
            Produit.objects.create(code_sage=code, nom=code, prix_unitaire=1, stock_disponible=1)
        suivante = importlib.import_module("catalogue.migrations.0006_betadine_benzoate_injectables")

        self.migration.classer(django_apps, None)
        suivante.ranger_en_injectables(django_apps, None)

        for code in codes:
            self.assertEqual(Produit.objects.get(code_sage=code).rayon.slug, "injectables", code)

    def test_le_classement_couvre_les_60_produits_du_fichier_sans_doublon(self):
        codes = [c for liste in self.migration.CLASSEMENT.values() for c in liste]

        self.assertEqual(len(codes), 60)
        self.assertEqual(len(set(codes)), 60)


class RayonAutresTests(TestCase):
    """Les produits sans rayon sont regroupés dans un rayon « Autres » du catalogue."""

    def setUp(self):
        from accounts.models import FormationSanitaire

        fosa = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        FormationSanitaire.objects.create(user=fosa, nom="CSI Test")
        self.client.force_login(fosa)
        comprimes = Rayon.objects.get(slug="comprimes")
        Produit.objects.create(code_sage="RANGE", nom="Rangé", prix_unitaire=1, stock_disponible=5, rayon=comprimes)
        Produit.objects.create(code_sage="ORPHELIN", nom="Orphelin", prix_unitaire=1, stock_disponible=5)
        Produit.objects.create(code_sage="EPUISE", nom="Épuisé", prix_unitaire=1, stock_disponible=0)

    def test_autres_apparait_en_fin_de_liste_avec_les_produits_disponibles_sans_rayon(self):
        rayons = self.client.get(reverse("catalogue:liste")).context["rayons"]

        self.assertEqual((rayons[-1].slug, rayons[-1].nb_produits), ("autres", 1))

    def test_filtrer_sur_autres_ne_montre_que_les_produits_sans_rayon(self):
        reponse = self.client.get(reverse("catalogue:liste"), {"rayon": "autres"})

        self.assertEqual([p.code_sage for p in reponse.context["produits"]], ["ORPHELIN"])
        self.assertEqual(reponse.context["rayon_actif"].nom, "Autres")

    def test_pas_de_rayon_autres_quand_tout_est_range(self):
        Produit.objects.filter(code_sage="ORPHELIN").update(rayon=Rayon.objects.get(slug="sirops"))

        rayons = self.client.get(reverse("catalogue:liste")).context["rayons"]

        self.assertNotIn("autres", [r.slug for r in rayons])


class MigrationRayonsLaboratoireMaterielTests(TestCase):
    def setUp(self):
        self.migration = importlib.import_module("catalogue.migrations.0007_rayons_laboratoire_materiel_et_classement")

    def test_cree_les_deux_rayons_et_range_selon_le_fichier(self):
        # Codes du fichier : un test VIH (Laboratoire), une insuline (chaîne du froid, choix FRPS).
        lignes = list(csv.DictReader(open(self.migration.CSV_PATH, encoding="utf-8-sig"), delimiter=";"))
        rayon_de = {ligne["code_sage"]: ligne["rayon"] for ligne in lignes}
        code_labo = next(c for c, r in rayon_de.items() if r == "laboratoire")
        Produit.objects.create(code_sage=code_labo, nom="labo", prix_unitaire=1, stock_disponible=1)

        self.migration.classer(django_apps, None)

        self.assertEqual(Produit.objects.get(code_sage=code_labo).rayon.nom, "Laboratoire")
        self.assertTrue(Rayon.objects.filter(slug="materiel", nom="Matériel").exists())

    def test_n_ecrase_pas_un_rayon_existant(self):
        lignes = list(csv.DictReader(open(self.migration.CSV_PATH, encoding="utf-8-sig"), delimiter=";"))
        code = lignes[0]["code_sage"]
        kits = Rayon.objects.get(slug="kits")
        Produit.objects.create(code_sage=code, nom="x", prix_unitaire=1, stock_disponible=1, rayon=kits)

        self.migration.classer(django_apps, None)

        self.assertEqual(Produit.objects.get(code_sage=code).rayon, kits)

    def test_le_fichier_ne_cite_que_des_rayons_connus_sans_doublon(self):
        lignes = list(csv.DictReader(open(self.migration.CSV_PATH, encoding="utf-8-sig"), delimiter=";"))
        connus = {"injectables", "comprimes", "sirops", "solutes", "consommables-medicaux",
                  "sante-de-reproduction", "kits", "papeterie-et-froid", "application-externe",
                  "laboratoire", "materiel"}

        self.assertTrue({ligne["rayon"] for ligne in lignes} <= connus)
        self.assertEqual(len({ligne["code_sage"] for ligne in lignes}), len(lignes))
