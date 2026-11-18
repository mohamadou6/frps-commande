from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commandes_services
from commandes.models import LigneCommande

from .services import donnees_tableau_de_bord


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class StatistiquesTests(TestCase):
    """Les chiffres ne comptent que ce qui a réellement été servi : ni les paniers,
    ni les lignes d'une commande hors connexion que le stock n'a pas permis de servir."""

    def setUp(self):
        self.stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Stats", district="Garoua 1")
        inactive = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa_muette = FormationSanitaire.objects.create(user=inactive, nom="CSI Muette", district="Garoua 1")
        self.para = Produit.objects.create(code_sage="S1", nom="Paracetamol", prix_unitaire=Decimal("100"), stock_disponible=100)
        self.amox = Produit.objects.create(code_sage="S2", nom="Amoxicilline", prix_unitaire=Decimal("250"), stock_disponible=100)

        commande = commandes_services.get_panier(self.fosa)
        commandes_services.ajouter_produit(commande, self.para, 10)
        commandes_services.confirmer_commande(commande)
        self.commande = commande
        # Ligne non servie (hors connexion, stock épuisé à l'arrivée) : ne compte pas.
        LigneCommande.objects.create(
            commande=commande, produit=self.amox, quantite=0, quantite_demandee=5, prix_unitaire_snapshot=Decimal("250")
        )
        # Un panier (brouillon) ne compte pas non plus.
        panier = commandes_services.get_panier(self.fosa)
        commandes_services.ajouter_produit(panier, self.amox, 30)

    def test_tableau_de_bord_ne_compte_que_le_servi(self):
        aujourdhui = date.today()
        donnees = donnees_tableau_de_bord(aujourdhui, aujourdhui)
        self.assertEqual(donnees["nb_commandes_periode"], 1)
        self.assertEqual(donnees["montant_periode"], Decimal("1000"))
        self.assertEqual([p["produit__nom"] for p in donnees["top_produits_periode"]], ["Paracetamol"])
        self.assertEqual(donnees["nb_fosa_sans_commande"], 1)
        self.assertEqual(donnees["fosa_sans_commande"], [self.fosa_muette])

    def test_pages_ouvertes_au_personnel(self):
        self.client.force_login(self.stock)
        for nom in ("index", "par_produit", "par_fosa", "par_district", "stock"):
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(f"statistiques:{nom}")).status_code, 200)

    def test_pages_fermees_aux_fosa(self):
        self.client.force_login(self.fosa.user)
        for nom in ("index", "par_produit", "par_fosa", "par_district", "stock"):
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(f"statistiques:{nom}")).status_code, 403)

    def test_statistiques_par_produit(self):
        self.client.force_login(self.stock)
        reponse = self.client.get(reverse("statistiques:par_produit"), {"produit": self.amox.pk})
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, "CSI Stats")  # demandé hors connexion mais jamais servi

    def test_export_excel_par_produit(self):
        self.client.force_login(self.stock)
        reponse = self.client.get(reverse("statistiques:par_produit"), {"produit": self.para.pk, "export": "xlsx"})
        self.assertEqual(
            reponse["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        self.assertIn(f"statistiques_produit_{self.para.pk}.xlsx", reponse["Content-Disposition"])

    def test_export_excel_par_fosa(self):
        self.client.force_login(self.stock)
        reponse = self.client.get(reverse("statistiques:par_fosa"), {"fosa": self.fosa.pk, "export": "xlsx"})
        self.assertEqual(reponse.status_code, 200)
