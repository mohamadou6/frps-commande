import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as django_apps
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from notifications.models import SMSLog
from notifications.services import numero_international

from . import services
from .models import Commande, EtapeTraitement


def _commande_confirmee(formation, produit, quantite=2):
    commande = services.get_panier(formation)
    services.ajouter_produit(commande, produit, quantite)
    services.confirmer_commande(commande)
    commande.refresh_from_db()
    return commande


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class SuiviCommandeTests(TestCase):
    """Le personnel stock fait avancer une commande validée : reçue → en préparation →
    prête → livrée. La FOSA est prévenue par SMS quand elle est prête."""

    def setUp(self):
        self.stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        self.compta = User.objects.create_user(username="compta", password="x", role=Role.PERSONNEL_COMPTABILITE)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(
            user=fosa_user, nom="CSI Suivi", telephone_contact="699 00 00 01"
        )
        self.produit = Produit.objects.create(
            code_sage="SUIVI", nom="Paracetamol", prix_unitaire=Decimal("500"), stock_disponible=50
        )
        self.commande = _commande_confirmee(self.formation, self.produit)

    def _avancer(self, etape, user=None):
        self.client.force_login(user or self.stock)
        return self.client.post(reverse("commandes:avancer_etape", args=[self.commande.pk]), {"etape": etape})

    def test_une_commande_validee_commence_a_l_etape_recue(self):
        self.assertEqual(self.commande.etape, EtapeTraitement.RECUE)
        self.assertEqual(self.commande.etape_suivante, EtapeTraitement.EN_PREPARATION)

    def test_les_etapes_s_enchainent_et_sont_datees(self):
        for etape in (EtapeTraitement.EN_PREPARATION, EtapeTraitement.PRETE, EtapeTraitement.LIVREE):
            self._avancer(etape)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.etape, EtapeTraitement.LIVREE)
        self.assertIsNotNone(self.commande.date_preparation)
        self.assertIsNotNone(self.commande.date_prete)
        self.assertIsNotNone(self.commande.date_livraison)
        self.assertIsNone(self.commande.etape_suivante)

    def test_un_double_clic_ne_saute_pas_d_etape(self):
        self._avancer(EtapeTraitement.EN_PREPARATION)
        self._avancer(EtapeTraitement.EN_PREPARATION)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.etape, EtapeTraitement.EN_PREPARATION)

    def test_la_fosa_recoit_un_sms_quand_la_commande_est_prete(self):
        self._avancer(EtapeTraitement.EN_PREPARATION)
        self.assertFalse(SMSLog.objects.filter(type_evenement="commande_prete").exists())
        self._avancer(EtapeTraitement.PRETE)
        sms = SMSLog.objects.get(type_evenement="commande_prete")
        self.assertEqual(sms.destinataire, "+237699000001")
        self.assertIn(f"#{self.commande.pk}", sms.message)
        self.assertIn("prete", sms.message)

    def test_sans_numero_l_etape_avance_quand_meme(self):
        self.formation.telephone_contact = ""
        self.formation.save()
        self._avancer(EtapeTraitement.EN_PREPARATION)
        self._avancer(EtapeTraitement.PRETE)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.etape, EtapeTraitement.PRETE)
        self.assertFalse(SMSLog.objects.filter(type_evenement="commande_prete").exists())

    def test_la_comptabilite_consulte_sans_pouvoir_avancer(self):
        self.client.force_login(self.compta)
        self.assertEqual(self.client.get(reverse("commandes:suivi")).status_code, 200)
        self.assertEqual(self._avancer(EtapeTraitement.EN_PREPARATION, user=self.compta).status_code, 403)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.etape, EtapeTraitement.RECUE)

    def test_une_fosa_n_accede_pas_au_suivi(self):
        self.client.force_login(self.formation.user)
        self.assertEqual(self.client.get(reverse("commandes:suivi")).status_code, 403)
        self.assertEqual(self._avancer(EtapeTraitement.EN_PREPARATION, user=self.formation.user).status_code, 403)

    def test_un_brouillon_ne_peut_pas_avancer(self):
        panier = services.get_panier(self.formation)
        with self.assertRaises(ValueError):
            services.avancer_etape(panier, EtapeTraitement.EN_PREPARATION)

    def test_la_liste_de_travail_cache_les_commandes_livrees(self):
        for etape in (EtapeTraitement.EN_PREPARATION, EtapeTraitement.PRETE, EtapeTraitement.LIVREE):
            self._avancer(etape)
        reponse = self.client.get(reverse("commandes:suivi"))
        self.assertNotIn(self.commande, reponse.context["commandes"])
        reponse = self.client.get(reverse("commandes:suivi") + "?etape=livree")
        self.assertIn(self.commande, reponse.context["commandes"])

    def test_le_compteur_nouvelles_suit_la_commande_d_etape_en_etape(self):
        self.client.force_login(self.stock)
        compteurs = lambda: {code: n for code, _l, n in self.client.get(reverse("commandes:suivi")).context["filtres"]}
        libelles = {code: l for code, l, _n in self.client.get(reverse("commandes:suivi")).context["filtres"]}
        self.assertEqual(libelles[EtapeTraitement.RECUE], "Nouvelles")
        self.assertEqual(compteurs()[EtapeTraitement.RECUE], 1)
        self._avancer(EtapeTraitement.EN_PREPARATION)
        apres = compteurs()
        self.assertEqual((apres[EtapeTraitement.RECUE], apres[EtapeTraitement.EN_PREPARATION]), (0, 1))
        self.assertEqual(apres["a_traiter"], 1)

    def test_retour_vers_une_adresse_externe_refuse(self):
        self.client.force_login(self.stock)
        reponse = self.client.post(
            reverse("commandes:avancer_etape", args=[self.commande.pk]),
            {"etape": EtapeTraitement.EN_PREPARATION, "suivant": "//exemple.com/"},
        )
        self.assertRedirects(reponse, reverse("commandes:suivi"))

    def test_la_fosa_voit_l_etape_sur_sa_commande(self):
        self._avancer(EtapeTraitement.EN_PREPARATION)
        self.client.force_login(self.formation.user)
        self.assertContains(self.client.get(reverse("commandes:historique")), "En préparation")
        self.assertContains(self.client.get(reverse("commandes:detail", args=[self.commande.pk])), "suivi-etapes")

    def test_la_migration_classe_les_anciennes_commandes_livrees(self):
        migration = importlib.import_module("commandes.migrations.0004_suivi_commande")
        ancienne = _commande_confirmee(self.formation, self.produit, 1)
        Commande.objects.filter(pk=ancienne.pk).update(date_confirmation=timezone.now() - timedelta(days=30))

        migration.classer_commandes_existantes(django_apps, None)

        ancienne.refresh_from_db()
        self.commande.refresh_from_db()
        self.assertEqual(ancienne.etape, EtapeTraitement.LIVREE)
        self.assertEqual(self.commande.etape, EtapeTraitement.RECUE)


class NumeroInternationalTests(TestCase):
    def test_formats_saisis_a_la_main(self):
        self.assertEqual(numero_international("699 00 00 01"), "+237699000001")
        self.assertEqual(numero_international("+237 699-00-00-01"), "+237699000001")
        self.assertEqual(numero_international("00237699000001"), "+237699000001")
        self.assertEqual(numero_international("237699000001"), "+237699000001")


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class RecommanderTests(TestCase):
    def setUp(self):
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Recommande")
        self.para = Produit.objects.create(
            code_sage="P1", nom="Paracetamol", prix_unitaire=Decimal("100"), stock_disponible=50
        )
        self.amox = Produit.objects.create(
            code_sage="P2", nom="Amoxicilline", prix_unitaire=Decimal("200"), stock_disponible=50
        )
        commande = services.get_panier(self.formation)
        services.ajouter_produit(commande, self.para, 10)
        services.ajouter_produit(commande, self.amox, 5)
        services.confirmer_commande(commande)
        self.ancienne = commande
        self.client.force_login(fosa_user)

    def _recommander(self):
        return self.client.post(reverse("commandes:recommander", args=[self.ancienne.pk]))

    def _panier(self):
        return {ligne.produit_id: ligne.quantite for ligne in services.get_panier(self.formation).lignes.all()}

    def test_remet_les_produits_au_panier_sans_valider(self):
        reponse = self._recommander()
        self.assertRedirects(reponse, reverse("commandes:panier"))
        self.assertEqual(self._panier(), {self.para.pk: 10, self.amox.pk: 5})
        self.para.refresh_from_db()
        self.assertEqual(self.para.stock_disponible, 40)  # rien n'est débité tant que la FOSA ne valide pas

    def test_plafonne_au_stock_et_ignore_l_indisponible(self):
        Produit.objects.filter(pk=self.para.pk).update(stock_disponible=3)
        Produit.objects.filter(pk=self.amox.pk).update(actif=False)
        self._recommander()
        self.assertEqual(self._panier(), {self.para.pk: 3})

    def test_s_ajoute_a_ce_qui_est_deja_au_panier(self):
        services.ajouter_produit(services.get_panier(self.formation), self.para, 4)
        self._recommander()
        self.assertEqual(self._panier()[self.para.pk], 14)

    def test_reprend_la_quantite_demandee_hors_connexion(self):
        ligne = self.ancienne.lignes.get(produit=self.para)
        ligne.quantite_demandee = 25
        ligne.save()
        self._recommander()
        self.assertEqual(self._panier()[self.para.pk], 25)

    def test_rien_de_disponible_ne_mene_pas_au_panier(self):
        Produit.objects.update(stock_disponible=0)
        reponse = self._recommander()
        self.assertRedirects(reponse, reverse("commandes:detail", args=[self.ancienne.pk]))
        self.assertEqual(self._panier(), {})

    def test_une_autre_fosa_ne_peut_pas_recommander_ma_commande(self):
        autre = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        FormationSanitaire.objects.create(user=autre, nom="CSI Autre")
        self.client.force_login(autre)
        self.assertEqual(self._recommander().status_code, 404)

    def test_un_simple_get_ne_fait_rien(self):
        self.client.get(reverse("commandes:recommander", args=[self.ancienne.pk]))
        self.assertEqual(self._panier(), {})
