from decimal import Decimal

from django.test import TestCase, override_settings

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from notifications.models import SMSLog

from . import services
from .models import StatutCommande


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class CommandeWorkflowTests(TestCase):
    def setUp(self):
        self.personnel_stock = User.objects.create_user(
            username="stock", password="x", role=Role.PERSONNEL_STOCK, telephone="+237600000001"
        )
        formation_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=formation_user, nom="CSI Test")
        self.produit = Produit.objects.create(
            code_sage="MED-TEST", nom="Test", prix_unitaire=Decimal("1000"), stock_disponible=10
        )

    def test_ajouter_produit_respecte_le_stock(self):
        commande = services.get_panier(self.formation)
        with self.assertRaises(services.StockInsuffisantError):
            services.ajouter_produit(commande, self.produit, 20)

    def test_confirmer_commande_notifie_personnel_stock(self):
        commande = services.get_panier(self.formation)
        services.ajouter_produit(commande, self.produit, 2)

        services.confirmer_commande(commande)

        commande.refresh_from_db()
        self.assertEqual(commande.statut, StatutCommande.CONFIRMEE)
        self.assertEqual(commande.montant_total, Decimal("2000"))
        sms = SMSLog.objects.get(destinataire="+237600000001")
        self.assertIn("Test x2", sms.message)
        self.assertIn("2000", sms.message)

    def test_confirmer_panier_vide_leve_une_erreur(self):
        commande = services.get_panier(self.formation)
        with self.assertRaises(ValueError):
            services.confirmer_commande(commande)


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class TelechargerPdfTests(TestCase):
    def setUp(self):
        formation_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=formation_user, nom="CSI Test")
        autre_user = User.objects.create_user(username="autre", password="x", role=Role.FORMATION_SANITAIRE)
        FormationSanitaire.objects.create(user=autre_user, nom="Autre FOSA")
        produit = Produit.objects.create(
            code_sage="MED-TEST", nom="Test", prix_unitaire=Decimal("1000"), stock_disponible=10
        )
        commande = services.get_panier(self.formation)
        services.ajouter_produit(commande, produit, 1)
        services.confirmer_commande(commande)
        self.commande = commande
        self.formation_user = formation_user
        self.autre_user = autre_user

    def test_le_proprietaire_peut_telecharger_le_pdf(self):
        self.client.force_login(self.formation_user)
        response = self.client.get(f"/panier/{self.commande.pk}/telecharger/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_un_autre_utilisateur_ne_peut_pas_telecharger(self):
        self.client.force_login(self.autre_user)
        response = self.client.get(f"/panier/{self.commande.pk}/telecharger/")

        self.assertEqual(response.status_code, 404)
