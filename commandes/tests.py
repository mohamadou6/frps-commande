import contextlib
import importlib
import io
from decimal import Decimal

from django.apps import apps as django_apps
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from frps_project.formatage import formater_montant
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


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class ArrondiDesMontantsTests(TestCase):
    """Le prix unitaire et le total de chaque ligne gardent leurs décimales ; seul le
    total général est arrondi au FCFA — en base, pas seulement à l'écran, sinon le
    solde d'une commande réglée ne tombe jamais à zéro."""

    def setUp(self):
        self.fosa_user = User.objects.create_user(
            username="csi-arrondi", password="x", role=Role.FORMATION_SANITAIRE
        )
        self.formation = FormationSanitaire.objects.create(user=self.fosa_user, nom="CSI Arrondi")

    def _commande(self, *lignes):
        commande = services.get_panier(self.formation)
        for code, prix, quantite in lignes:
            produit = Produit.objects.create(
                code_sage=code, nom=code, prix_unitaire=Decimal(prix), stock_disponible=100
            )
            services.ajouter_produit(commande, produit, quantite)
        return commande

    def test_le_total_general_est_arrondi_les_lignes_gardent_leurs_decimales(self):
        commande = self._commande(("A", "419.10", 3), ("B", "42.24", 10), ("C", "12.80", 3))

        services.confirmer_commande(commande)

        commande.refresh_from_db()
        self.assertEqual(
            sorted(ligne.sous_total for ligne in commande.lignes.all()),
            [Decimal("38.40"), Decimal("422.40"), Decimal("1257.30")],
        )
        self.assertEqual(commande.montant_total, Decimal("1718"))  # 1 718,10 au centime près

    def test_un_total_en_virgule_cinquante_monte_au_franc_superieur(self):
        """`round()` de Python arrondit au pair : 12 344,50 donnait 12 344 sur le PDF
        quand l'écran affichait 12 345."""
        commande = self._commande(("D", "12344.50", 1))

        commande.refresh_from_db()
        self.assertEqual(commande.montant_total, Decimal("12345"))
        self.assertEqual(formater_montant(Decimal("12344.50")), "12 345")

    def test_la_page_affiche_la_ligne_avec_decimales_et_le_total_arrondi(self):
        commande = self._commande(("A", "419.10", 3), ("B", "42.24", 10), ("C", "12.80", 3))
        services.confirmer_commande(commande)
        self.client.force_login(self.fosa_user)

        page = self.client.get(reverse("commandes:detail", args=[commande.pk])).content.decode()

        self.assertIn("1\xa0257,30 FCFA", page)
        self.assertIn("Total : 1\xa0718 FCFA", page)

    def test_la_migration_arrondit_les_commandes_deja_passees(self):
        commande = self._commande(("E", "1718.60", 1))
        Commande.objects.filter(pk=commande.pk).update(montant_total=Decimal("1718.60"))
        migration = importlib.import_module("commandes.migrations.0002_arrondir_montants_totaux")

        with contextlib.redirect_stdout(io.StringIO()):
            migration.arrondir_montants_totaux(django_apps, None)

        commande.refresh_from_db()
        self.assertEqual(commande.montant_total, Decimal("1719"))
