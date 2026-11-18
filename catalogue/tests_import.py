import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import Role, User

from .models import Produit


def _classeur(entetes, lignes, nom="produits.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.append(entetes)
    for ligne in lignes:
        ws.append(list(ligne))
    contenu = io.BytesIO()
    wb.save(contenu)
    return SimpleUploadedFile(nom, contenu.getvalue())


class ImportProduitsTests(TestCase):
    """Import Excel des prix et du stock par l'admin FRPS : la seule façon de mettre
    le catalogue à jour, une erreur ici touche directement ce que voient les FOSA."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        self.produit = Produit.objects.create(
            code_sage="AMOX500", nom="Amoxicilline 500", prix_unitaire=Decimal("100"), stock_disponible=10
        )
        self.client.force_login(self.admin)

    def _importer(self, fichier):
        return self.client.post(reverse("catalogue:importer"), {"fichier": fichier})

    def test_met_a_jour_prix_et_stock(self):
        self._importer(_classeur(["code_sage", "prix_unitaire", "stock_disponible"], [("AMOX500", 125.5, 40)]))
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.prix_unitaire, Decimal("125.50"))
        self.assertEqual(self.produit.stock_disponible, 40)

    def test_colonnes_dans_un_autre_ordre_et_intitules_proches(self):
        self._importer(_classeur(["Stock", "Code article", "Prix de vente"], [(7, "AMOX500", 90)]))
        self.produit.refresh_from_db()
        self.assertEqual((self.produit.prix_unitaire, self.produit.stock_disponible), (Decimal("90.00"), 7))

    def test_cree_un_produit_inconnu_avec_son_nom(self):
        self._importer(
            _classeur(["code_sage", "nom", "prix_unitaire", "stock_disponible"], [("NOUV1", "Zinc 20mg", 50, 3)])
        )
        nouveau = Produit.objects.get(code_sage="NOUV1")
        self.assertEqual((nouveau.nom, nouveau.prix_unitaire, nouveau.stock_disponible), ("Zinc 20mg", Decimal("50.00"), 3))

    def test_lignes_vides_et_codes_vides_ignores(self):
        self._importer(
            _classeur(["code_sage", "prix_unitaire", "stock_disponible"], [(None, None, None), ("", 10, 10), ("AMOX500", 100, 11)])
        )
        self.assertEqual(Produit.objects.count(), 1)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 11)

    def test_colonne_manquante_ne_change_rien(self):
        reponse = self._importer(_classeur(["code_sage", "prix_unitaire"], [("AMOX500", 999)]))
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.prix_unitaire, Decimal("100"))
        self.assertContains(reponse, "Colonnes introuvables")

    def test_un_fichier_qui_n_est_pas_excel_est_refuse(self):
        reponse = self._importer(SimpleUploadedFile("produits.csv", b"code_sage;prix;stock\nAMOX500;1;1\n"))
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 10)
        self.assertContains(reponse, ".xlsx")

    def test_reserve_a_l_admin(self):
        stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        self.client.force_login(stock)
        reponse = self._importer(_classeur(["code_sage", "prix_unitaire", "stock_disponible"], [("AMOX500", 1, 1)]))
        self.assertEqual(reponse.status_code, 403)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.prix_unitaire, Decimal("100"))
