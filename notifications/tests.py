from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commande_services
from paiements import services as paiement_services

from .models import Notification
from .pdf import generer_pdf_commande, generer_token_pdf, verifier_token_pdf


class PdfCommandeTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        formation_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=formation_user, nom="CSI Test")
        produit = Produit.objects.create(
            code_sage="MED-TEST", nom="Test", prix_unitaire=Decimal("1000"), stock_disponible=10
        )
        self.commande = commande_services.get_panier(self.formation)
        commande_services.ajouter_produit(self.commande, produit, 2)
        commande_services.confirmer_commande(self.commande)

    def test_token_valide_pour_la_bonne_commande_seulement(self):
        token = generer_token_pdf(self.commande.pk)
        self.assertTrue(verifier_token_pdf(self.commande.pk, token))
        self.assertFalse(verifier_token_pdf(self.commande.pk + 999, token))
        self.assertFalse(verifier_token_pdf(self.commande.pk, "token-invalide"))

    def test_generer_pdf_commande_produit_des_octets_pdf(self):
        pdf_bytes = generer_pdf_commande(self.commande)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_endpoint_pdf_public_sert_le_fichier_avec_un_token_valide(self):
        token = generer_token_pdf(self.commande.pk)
        url = reverse("commandes:pdf", args=[self.commande.pk, token])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_endpoint_pdf_refuse_un_token_invalide(self):
        url = reverse("commandes:pdf", args=[self.commande.pk, "token-invalide"])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log", PAYMENT_GATEWAY="mock")
class NotificationInterneTests(TestCase):
    def setUp(self):
        self.stock_user = User.objects.create_user(username="stock2", password="x", role=Role.PERSONNEL_STOCK)
        self.compta_user = User.objects.create_user(username="compta2", password="x", role=Role.PERSONNEL_COMPTABILITE)
        formation_user = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=formation_user, nom="CSI Test 2")
        self.produit = Produit.objects.create(
            code_sage="MED-TEST2", nom="Test2", prix_unitaire=Decimal("1000"), stock_disponible=10
        )

    def _confirmer_commande(self):
        commande = commande_services.get_panier(self.formation)
        commande_services.ajouter_produit(commande, self.produit, 2)
        commande_services.confirmer_commande(commande)
        return commande

    def test_confirmer_commande_cree_une_notification_pour_personnel_stock(self):
        commande = self._confirmer_commande()

        notif = Notification.objects.get(commande=commande, role_cible=Role.PERSONNEL_STOCK)
        self.assertFalse(notif.lu)
        self.assertIn("Test2 x2", notif.message)

    def test_paiement_confirme_cree_une_notification_pour_comptabilite(self):
        commande = self._confirmer_commande()
        paiement_services.payer_en_especes(commande)

        notif = Notification.objects.get(commande=commande, role_cible=Role.PERSONNEL_COMPTABILITE)
        self.assertFalse(notif.lu)

    def test_liste_ne_montre_que_les_notifications_du_role(self):
        commande = self._confirmer_commande()
        paiement_services.payer_en_especes(commande)

        self.client.force_login(self.stock_user)
        response = self.client.get(reverse("notifications:liste"))

        self.assertContains(response, "Nouvelle commande")
        self.assertNotContains(response, "Paiement reçu")

    def test_formation_sanitaire_ne_peut_pas_voir_les_notifications(self):
        self.client.force_login(self.formation.user)
        response = self.client.get(reverse("notifications:liste"))

        self.assertEqual(response.status_code, 403)

    def test_marquer_lu(self):
        commande = self._confirmer_commande()
        notif = Notification.objects.get(commande=commande, role_cible=Role.PERSONNEL_STOCK)

        self.client.force_login(self.stock_user)
        response = self.client.post(reverse("notifications:marquer_lu", args=[notif.pk]))

        notif.refresh_from_db()
        self.assertTrue(notif.lu)
        self.assertEqual(response.status_code, 302)

    def test_un_role_ne_peut_pas_marquer_lu_la_notification_dun_autre_role(self):
        commande = self._confirmer_commande()
        notif = Notification.objects.get(commande=commande, role_cible=Role.PERSONNEL_STOCK)

        self.client.force_login(self.compta_user)
        response = self.client.post(reverse("notifications:marquer_lu", args=[notif.pk]))

        notif.refresh_from_db()
        self.assertFalse(notif.lu)
        self.assertEqual(response.status_code, 404)
