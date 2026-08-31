from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from notifications.models import SMSLog

from . import services
from .models import Commande, StatutCommande


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
        self.assertIn("2 000", sms.message)

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


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class SupprimerCommandeTests(TestCase):
    """Suppression d'une commande validée par erreur par une FOSA, réservée à l'admin.
    L'enjeu est le stock : il est débité à la confirmation, pas rendu à la suppression."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin-sup", password="x", role=Role.ADMIN)
        self.stock_user = User.objects.create_user(
            username="stock-sup", password="x", role=Role.PERSONNEL_STOCK
        )
        fosa_user = User.objects.create_user(username="csi-sup", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Suppression")
        self.produit = Produit.objects.create(
            code_sage="MED-SUP", nom="Produit Sup", prix_unitaire=Decimal("100"), stock_disponible=50
        )

    def _commande_confirmee(self, quantite=10):
        commande = services.get_panier(self.formation)
        services.ajouter_produit(commande, self.produit, quantite)
        services.confirmer_commande(commande)
        return commande

    def test_supprimer_une_commande_confirmee_remet_le_stock(self):
        commande = self._commande_confirmee(10)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 40)  # débité à la confirmation

        services.supprimer_commande(commande)

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 50)  # revenu à l'état initial
        self.assertFalse(Commande.objects.filter(pk=commande.pk).exists())

    def test_supprimer_un_brouillon_ne_gonfle_pas_le_stock(self):
        """Un brouillon n'a jamais débité le stock : le recréditer le fausserait."""
        commande = services.get_panier(self.formation)
        services.ajouter_produit(commande, self.produit, 10)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 50)

        services.supprimer_commande(commande)

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 50)

    def test_admin_peut_supprimer_via_le_bouton(self):
        commande = self._commande_confirmee(10)
        self.client.force_login(self.admin)

        reponse = self.client.post(reverse("commandes:supprimer", args=[commande.pk]))

        self.assertEqual(reponse.status_code, 302)
        self.assertFalse(Commande.objects.filter(pk=commande.pk).exists())
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_disponible, 50)

    def test_personnel_non_admin_ne_peut_pas_supprimer(self):
        commande = self._commande_confirmee(10)
        self.client.force_login(self.stock_user)

        reponse = self.client.post(reverse("commandes:supprimer", args=[commande.pk]))

        self.assertEqual(reponse.status_code, 403)
        self.assertTrue(Commande.objects.filter(pk=commande.pk).exists())

    def test_fosa_ne_peut_pas_supprimer_sa_propre_commande(self):
        commande = self._commande_confirmee(10)
        self.client.force_login(self.formation.user)

        reponse = self.client.post(reverse("commandes:supprimer", args=[commande.pk]))

        self.assertEqual(reponse.status_code, 403)
        self.assertTrue(Commande.objects.filter(pk=commande.pk).exists())

    def test_un_simple_GET_ne_supprime_rien(self):
        """Un lien visité — ou préchargé par le navigateur — ne doit rien détruire."""
        commande = self._commande_confirmee(10)
        self.client.force_login(self.admin)

        reponse = self.client.get(reverse("commandes:supprimer", args=[commande.pk]))

        self.assertEqual(reponse.status_code, 405)
        self.assertTrue(Commande.objects.filter(pk=commande.pk).exists())

    def test_le_bouton_n_apparait_que_pour_l_admin(self):
        self._commande_confirmee(10)

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("statistiques:index")), "Supprimer")

        self.client.force_login(self.stock_user)
        self.assertNotContains(self.client.get(reverse("statistiques:index")), "Supprimer")
