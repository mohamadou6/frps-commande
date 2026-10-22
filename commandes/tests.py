import contextlib
import importlib
import io
import json
import uuid
from decimal import Decimal

from django.apps import apps as django_apps
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from frps_project.formatage import formater_montant, formater_prix
from notifications.models import SMSLog

from . import services
from .models import Commande, LigneCommande, StatutCommande


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


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class AjoutAuPanierSansRechargementTests(TestCase):
    """Le catalogue ajoute au panier sans recharger la page (js/app.js) : sur le réseau
    lent des FOSA, recharger tout le catalogue à chaque produit coûtait ~10 s."""

    AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

    def setUp(self):
        self.fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        FormationSanitaire.objects.create(user=self.fosa_user, nom="CSI Test")
        self.produit = Produit.objects.create(
            code_sage="MED-AJAX", nom="Paracetamol 500 mg", prix_unitaire=Decimal("1250.50"), stock_disponible=10
        )
        self.client.force_login(self.fosa_user)

    def _ajouter(self, quantite, **entetes):
        return self.client.post(
            reverse("commandes:ajouter", args=[self.produit.pk]), {"quantite": quantite}, **entetes
        )

    def test_ajout_instantane_repond_en_json_avec_le_panier_a_jour(self):
        reponse = self._ajouter("3", **self.AJAX)

        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        self.assertTrue(donnees["ok"])
        self.assertEqual(donnees["quantite"], "3")
        self.assertEqual(donnees["panier_nb"], 1)
        self.assertEqual(donnees["panier_montant"], formater_montant(Decimal("3752")))
        self.assertFalse(donnees["panier_montant_nul"])

    def test_stock_insuffisant_renvoie_le_message_sans_rien_ajouter(self):
        reponse = self._ajouter("50", **self.AJAX)

        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(reponse.json()["ok"])
        self.assertIn("Stock insuffisant", reponse.json()["message"])
        self.assertFalse(Commande.objects.filter(lignes__produit=self.produit).exists())

    def test_quantite_illisible_donne_un_message_en_francais(self):
        reponse = self._ajouter("abc", **self.AJAX)

        self.assertEqual(reponse.json()["message"], "Quantité invalide.")

    def test_sans_javascript_le_formulaire_ramene_au_catalogue(self):
        reponse = self._ajouter("2")

        self.assertRedirects(reponse, reverse("catalogue:liste"), fetch_redirect_response=False)

    def test_le_catalogue_active_lajout_instantane_pour_la_fosa(self):
        page = self.client.get(reverse("catalogue:liste")).content.decode()

        self.assertIn("data-ajout-instantane", page)
        self.assertIn("form-ajout", page)

    def test_les_fiches_portent_le_produit_pour_l_ajout_sans_reseau(self):
        """js/app.js lit ces valeurs pour garder le produit sur le téléphone : le prix
        doit rester lisible par JavaScript (point décimal, sans séparateur de milliers)."""
        page = self.client.get(reverse("catalogue:liste")).content.decode()

        self.assertIn(f'data-produit-id="{self.produit.pk}"', page)
        self.assertIn('data-produit-prix="1250.50"', page)
        self.assertIn('data-produit-stock="10"', page)


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class CommandeHorsConnexionTests(TestCase):
    """Commande préparée sans réseau sur le téléphone (js/demandes.js), envoyée au retour
    du réseau, validée par le serveur à son arrivée. Trois risques : un renvoi qui
    double la commande et le débit, un stock qui a baissé entre-temps, un prix repris
    du téléphone."""

    def setUp(self):
        self.stock_user = User.objects.create_user(
            username="stock", password="x", role=Role.PERSONNEL_STOCK,
            telephone="+237600000001", email="stock@frpsno.com",
        )
        self.fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=self.fosa_user, nom="CSI Test")
        self.paracetamol = Produit.objects.create(
            code_sage="MED-P", nom="Paracetamol", prix_unitaire=Decimal("100.50"), stock_disponible=50
        )
        self.amoxicilline = Produit.objects.create(
            code_sage="MED-A", nom="Amoxicilline", prix_unitaire=Decimal("200"), stock_disponible=4
        )
        self.client.force_login(self.fosa_user)

    def _envoyer(self, lignes, uuid_client=None, **champs):
        corps = {"uuid": str(uuid_client or uuid.uuid4()), "compte": str(self.fosa_user.pk), "lignes": lignes}
        corps.update(champs)
        return self.client.post(
            reverse("commandes:synchroniser_demande"), data=json.dumps(corps), content_type="application/json"
        )

    def _stock(self, produit):
        produit.refresh_from_db()
        return produit.stock_disponible

    def test_la_demande_est_validee_a_son_arrivee(self):
        reponse = self._envoyer([{"produit": self.paracetamol.pk, "quantite": 10}])

        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        commande = Commande.objects.get(pk=donnees["commande_id"])
        self.assertEqual(commande.statut, StatutCommande.CONFIRMEE)
        self.assertIsNotNone(commande.date_confirmation)
        self.assertEqual(commande.montant_total, Decimal("1005"))
        self.assertEqual(self._stock(self.paracetamol), 40)
        self.assertEqual(donnees["lignes"], [
            {"produit": self.paracetamol.pk, "nom": "Paracetamol", "demandee": 10, "servie": 10,
             "prix_unitaire": formater_prix(Decimal("100.50"))},
        ])
        self.assertEqual(donnees["montant_total"], formater_montant(Decimal("1005")))
        self.assertFalse(donnees["deja_recue"])
        # Notifiée comme une commande passée en ligne.
        self.assertTrue(SMSLog.objects.filter(destinataire="+237600000001", commande=commande).exists())

    def test_un_renvoi_de_la_meme_demande_ne_cree_ni_doublon_ni_second_debit(self):
        """Réponse perdue (réseau coupé pendant l'envoi), ou envoi doublé par le service
        worker et la page au retour du réseau : le téléphone renvoie la même demande."""
        identifiant = uuid.uuid4()
        lignes = [{"produit": self.paracetamol.pk, "quantite": 10}]

        premiere = self._envoyer(lignes, uuid_client=identifiant).json()
        seconde = self._envoyer(lignes, uuid_client=identifiant).json()

        self.assertEqual(Commande.objects.filter(formation_sanitaire=self.formation).count(), 1)
        self.assertEqual(seconde["commande_id"], premiere["commande_id"])
        self.assertTrue(seconde["deja_recue"])
        self.assertEqual(self._stock(self.paracetamol), 40)  # débité une seule fois
        self.assertEqual(SMSLog.objects.count(), 1)  # notifiée une seule fois

    def test_stock_insuffisant_a_l_arrivee_sert_ce_qui_reste(self):
        """Le stock a baissé entre la préparation hors ligne et l'arrivée : on sert ce
        qui reste plutôt que de refuser toute la commande."""
        donnees = self._envoyer([
            {"produit": self.paracetamol.pk, "quantite": 2},
            {"produit": self.amoxicilline.pk, "quantite": 10},
        ]).json()

        commande = Commande.objects.get(pk=donnees["commande_id"])
        self.assertEqual(commande.statut, StatutCommande.CONFIRMEE)
        amox = commande.lignes.get(produit=self.amoxicilline)
        self.assertEqual((amox.quantite_demandee, amox.quantite), (10, 4))
        self.assertTrue(amox.servie_en_partie)
        self.assertEqual(self._stock(self.amoxicilline), 0)
        self.assertEqual(self._stock(self.paracetamol), 48)
        self.assertEqual(commande.montant_total, Decimal("1001"))  # 2 × 100,50 + 4 × 200

    def test_rien_de_disponible_annule_la_demande_sans_debit_ni_notification(self):
        Produit.objects.filter(pk=self.amoxicilline.pk).update(stock_disponible=0)

        donnees = self._envoyer([{"produit": self.amoxicilline.pk, "quantite": 3}]).json()

        commande = Commande.objects.get(pk=donnees["commande_id"])
        self.assertEqual(commande.statut, StatutCommande.ANNULEE)
        self.assertEqual(commande.montant_total, Decimal("0"))
        self.assertEqual(donnees["lignes"][0]["servie"], 0)
        self.assertEqual(self._stock(self.amoxicilline), 0)
        self.assertFalse(SMSLog.objects.exists())

    def test_le_prix_est_recalcule_au_serveur(self):
        """Le téléphone a vu un autre prix (catalogue enregistré), ou en envoie un faux :
        seul le prix du serveur au moment de la validation compte."""
        Produit.objects.filter(pk=self.paracetamol.pk).update(prix_unitaire=Decimal("150"))

        donnees = self._envoyer(
            [{"produit": self.paracetamol.pk, "quantite": 2, "prix": "1", "prix_unitaire": "1"}],
            montant_total="2",
        ).json()

        ligne = LigneCommande.objects.get(commande_id=donnees["commande_id"])
        self.assertEqual(ligne.prix_unitaire_snapshot, Decimal("150"))
        self.assertEqual(Commande.objects.get(pk=donnees["commande_id"]).montant_total, Decimal("300"))

    def test_un_produit_desactive_entre_temps_n_est_pas_servi(self):
        Produit.objects.filter(pk=self.amoxicilline.pk).update(actif=False)

        donnees = self._envoyer([
            {"produit": self.paracetamol.pk, "quantite": 1},
            {"produit": self.amoxicilline.pk, "quantite": 1},
        ]).json()

        servies = {ligne["produit"]: ligne["servie"] for ligne in donnees["lignes"]}
        self.assertEqual(servies, {self.paracetamol.pk: 1, self.amoxicilline.pk: 0})
        self.assertEqual(self._stock(self.amoxicilline), 4)

    def test_un_produit_supprime_du_catalogue_est_ignore(self):
        donnees = self._envoyer([
            {"produit": self.paracetamol.pk, "quantite": 1},
            {"produit": 999999, "quantite": 1},
        ]).json()

        self.assertEqual([ligne["produit"] for ligne in donnees["lignes"]], [self.paracetamol.pk])

    def test_le_meme_produit_en_double_est_additionne(self):
        donnees = self._envoyer([
            {"produit": self.paracetamol.pk, "quantite": 2},
            {"produit": self.paracetamol.pk, "quantite": 3},
        ]).json()

        self.assertEqual(donnees["lignes"][0]["demandee"], 5)

    def test_une_demande_restee_en_attente_est_terminee_au_renvoi(self):
        """Reçue mais pas validée (erreur entre les deux) : elle reste « en attente de
        validation », sans débit, et le renvoi automatique du téléphone la termine."""
        identifiant = uuid.uuid4()
        commande, _ = services.recevoir_demande(self.formation, identifiant, {self.paracetamol.pk: 5})
        self.assertEqual(commande.statut, StatutCommande.EN_ATTENTE_SYNCHRO)
        self.assertEqual(self._stock(self.paracetamol), 50)

        donnees = self._envoyer([{"produit": self.paracetamol.pk, "quantite": 5}], uuid_client=identifiant).json()

        self.assertEqual(donnees["commande_id"], commande.pk)
        self.assertEqual(donnees["statut"], StatutCommande.CONFIRMEE)
        self.assertEqual(self._stock(self.paracetamol), 45)

    def test_une_demande_en_attente_ne_compte_pas_comme_commande_effective(self):
        commande, _ = services.recevoir_demande(self.formation, uuid.uuid4(), {self.paracetamol.pk: 5})

        self.assertFalse(commande.est_effective)
        page = self.client.get(reverse("commandes:detail", args=[commande.pk])).content.decode()
        self.assertNotIn("Télécharger le PDF", page)
        self.assertIn("en cours de validation", page)

    def test_l_identifiant_d_une_autre_fosa_est_refuse_sans_rien_reveler(self):
        autre_user = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        autre = FormationSanitaire.objects.create(user=autre_user, nom="Autre FOSA")
        identifiant = uuid.uuid4()
        commande_autre, _ = services.synchroniser_demande(autre, identifiant, {self.paracetamol.pk: 1})

        reponse = self._envoyer([{"produit": self.paracetamol.pk, "quantite": 7}], uuid_client=identifiant)

        self.assertEqual(reponse.status_code, 400)
        self.assertNotIn("Autre FOSA", reponse.content.decode())
        self.assertFalse(Commande.objects.filter(formation_sanitaire=self.formation).exists())
        self.assertEqual(commande_autre.lignes.get().quantite_demandee, 1)

    def test_une_demande_preparee_sous_un_autre_compte_n_est_pas_traitee(self):
        """Téléphone partagé : la demande d'un compte ne part jamais sous la session d'un autre."""
        reponse = self._envoyer([{"produit": self.paracetamol.pk, "quantite": 1}], compte="123456")

        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.json()["code"], "autre_compte")
        self.assertFalse(Commande.objects.exists())

    def test_une_demande_illisible_est_refusee_sans_rien_creer(self):
        url = reverse("commandes:synchroniser_demande")
        envois = [
            json.dumps({"uuid": "pas-un-uuid", "lignes": [{"produit": self.paracetamol.pk, "quantite": 1}]}),
            json.dumps({"uuid": str(uuid.uuid4()), "lignes": []}),
            json.dumps({"uuid": str(uuid.uuid4()), "lignes": [{"produit": self.paracetamol.pk, "quantite": -1}]}),
            json.dumps({"uuid": str(uuid.uuid4()), "lignes": [{"produit": "x", "quantite": 1}]}),
            json.dumps([1, 2]),
            "pas du json",
        ]
        for corps in envois:
            with self.subTest(corps=corps):
                reponse = self.client.post(url, data=corps, content_type="application/json")
                self.assertEqual(reponse.status_code, 400)
        self.assertFalse(Commande.objects.exists())

    def test_un_simple_GET_ne_cree_rien(self):
        reponse = self.client.get(reverse("commandes:synchroniser_demande"))

        self.assertEqual(reponse.status_code, 405)

    def test_le_personnel_frps_ne_peut_pas_envoyer_de_demande(self):
        self.client.force_login(self.stock_user)

        reponse = self._envoyer([{"produit": self.paracetamol.pk, "quantite": 1}], compte=str(self.stock_user.pk))

        self.assertEqual(reponse.status_code, 302)
        self.assertFalse(Commande.objects.exists())

    def test_sans_session_la_demande_n_est_pas_traitee(self):
        """Le téléphone reçoit la page de connexion (pas du JSON) et garde sa demande."""
        self.client.logout()

        reponse = self._envoyer([{"produit": self.paracetamol.pk, "quantite": 1}])

        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse("login"), reponse["Location"])
        self.assertFalse(Commande.objects.exists())

    def test_le_detail_montre_le_demande_et_le_servi(self):
        donnees = self._envoyer([{"produit": self.amoxicilline.pk, "quantite": 10}]).json()

        page = self.client.get(reverse("commandes:detail", args=[donnees["commande_id"]])).content.decode()

        self.assertIn("<th>Demandé</th><th>Servi</th>", page)
        self.assertIn("préparée hors connexion", page)
        self.assertIn('class="quantite-reduite"', page)

    def test_l_historique_signale_la_commande_preparee_hors_connexion(self):
        self._envoyer([{"produit": self.paracetamol.pk, "quantite": 1}])

        page = self.client.get(reverse("commandes:historique")).content.decode()

        self.assertIn("📡 hors connexion", page)

    def test_les_lignes_non_servies_restent_hors_du_sms_et_de_l_email(self):
        Produit.objects.filter(pk=self.amoxicilline.pk).update(stock_disponible=0)

        donnees = self._envoyer([
            {"produit": self.paracetamol.pk, "quantite": 1},
            {"produit": self.amoxicilline.pk, "quantite": 3},
        ]).json()

        commande = Commande.objects.get(pk=donnees["commande_id"])
        self.assertEqual(commande.lignes.count(), 2)  # la FOSA voit le produit non servi
        self.assertEqual(list(commande.lignes.servies().values_list("produit", flat=True)), [self.paracetamol.pk])
        sms = SMSLog.objects.get(commande=commande)
        self.assertNotIn("Amoxicilline", sms.message)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("Amoxicilline", mail.outbox[0].body)

    def test_une_commande_en_ligne_garde_son_affichage(self):
        """Les colonnes Demandé/Servi ne concernent que les commandes hors connexion."""
        commande = services.get_panier(self.formation)
        services.ajouter_produit(commande, self.paracetamol, 2)
        services.confirmer_commande(commande)

        page = self.client.get(reverse("commandes:detail", args=[commande.pk])).content.decode()

        self.assertIn("<th>Quantité</th>", page)
        self.assertNotIn("Demandé", page)
        self.assertIn("Télécharger le PDF", page)
