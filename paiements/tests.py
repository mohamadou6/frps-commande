from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commande_services
from notifications.models import SMSLog, WhatsAppLog

from . import services
from .models import MethodePaiement, ReglementPaiement, StatutPaiement


@override_settings(WHATSAPP_BACKEND="log", SMS_BACKEND="log", PAYMENT_GATEWAY="mock")
class PaiementWorkflowTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="compta", password="x", role=Role.PERSONNEL_COMPTABILITE, telephone="+237600000002"
        )
        formation_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=formation_user, nom="CSI Test")
        self.produit = Produit.objects.create(
            code_sage="MED-TEST", nom="Test", prix_unitaire=Decimal("1000"), stock_disponible=10
        )
        commande = commande_services.get_panier(self.formation)
        commande_services.ajouter_produit(commande, self.produit, 2)
        commande_services.confirmer_commande(commande)
        self.commande = commande

    def test_confirmer_paiement_marque_commande_payee_et_notifie_comptabilite(self):
        paiement = services.initier_paiement(self.commande)
        services.confirmer_paiement(paiement, succes=True)

        self.commande.refresh_from_db()
        paiement.refresh_from_db()
        self.assertEqual(paiement.statut, StatutPaiement.CONFIRME)
        self.assertEqual(self.commande.statut, "payee")
        self.assertEqual(SMSLog.objects.filter(destinataire="+237600000002").count(), 1)

    def test_paiement_echoue_ne_notifie_pas(self):
        paiement = services.initier_paiement(self.commande)
        services.confirmer_paiement(paiement, succes=False)

        self.assertEqual(paiement.statut, StatutPaiement.ECHOUE)
        self.assertEqual(SMSLog.objects.filter(destinataire="+237600000002").count(), 0)

    def test_confirmer_paiement_ne_declenche_plus_l_envoi_whatsapp_automatique(self):
        """Le PDF est désormais téléchargé/partagé par la FOSA elle-même, plus envoyé par l'app."""
        paiement = services.initier_paiement(self.commande)
        services.confirmer_paiement(paiement, succes=True)

        self.assertEqual(WhatsAppLog.objects.filter(commande=self.commande).count(), 0)

    def test_payer_en_especes_valide_directement_sans_etape_supplementaire(self):
        paiement = services.payer_en_especes(self.commande)

        self.commande.refresh_from_db()
        self.assertEqual(paiement.methode, MethodePaiement.ESPECES)
        self.assertEqual(paiement.statut, StatutPaiement.CONFIRME)
        self.assertEqual(self.commande.statut, "payee")
        self.assertEqual(SMSLog.objects.filter(destinataire="+237600000002").count(), 1)


@override_settings(WHATSAPP_BACKEND="log", SMS_BACKEND="log", PAYMENT_GATEWAY="mock")
class DateDeReglementTests(TestCase):
    """La FOSA règle un jour, la comptabilité saisit parfois bien plus tard. C'est la
    date de paiement réelle qui fait foi, pas l'horodatage de la saisie."""

    def setUp(self):
        self.compta = User.objects.create_user(
            username="compta-date", password="x", role=Role.PERSONNEL_COMPTABILITE
        )
        fosa_user = User.objects.create_user(username="csi-date", password="x", role=Role.FORMATION_SANITAIRE)
        self.formation = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Date")
        self.produit = Produit.objects.create(
            code_sage="MED-DATE", nom="Produit Date", prix_unitaire=Decimal("1000"), stock_disponible=100
        )
        commande = commande_services.get_panier(self.formation)
        commande_services.ajouter_produit(commande, self.produit, 10)
        commande_services.confirmer_commande(commande)
        self.commande = commande
        # La commande est confirmée « aujourd'hui » : on recule sa date pour pouvoir
        # tester des règlements antérieurs à la saisie.
        self.commande.date_confirmation = timezone.now() - timedelta(days=30)
        self.commande.save(update_fields=["date_confirmation"])

    def _verser(self, montant, date_paiement=None, methode=MethodePaiement.ESPECES):
        return services.mettre_a_jour_paiement(
            self.commande, montant, self.compta, methode=methode, date_paiement=date_paiement
        )

    def test_la_date_saisie_est_conservee_telle_quelle(self):
        veille = timezone.localdate() - timedelta(days=5)

        self._verser("1000", date_paiement=veille.isoformat())

        reglement = ReglementPaiement.objects.get()
        self.assertEqual(reglement.date_paiement, veille)
        # L'horodatage de saisie, lui, reste celui d'aujourd'hui : c'est la piste d'audit.
        self.assertEqual(timezone.localtime(reglement.date_reglement).date(), timezone.localdate())

    def test_sans_date_fournie_le_jour_meme_est_retenu(self):
        self._verser("1000")

        self.assertEqual(ReglementPaiement.objects.get().date_paiement, timezone.localdate())

    def test_une_date_future_est_refusee(self):
        demain = timezone.localdate() + timedelta(days=1)

        with self.assertRaises(ValueError) as erreur:
            self._verser("1000", date_paiement=demain.isoformat())

        self.assertIn("futur", str(erreur.exception))
        self.assertEqual(ReglementPaiement.objects.count(), 0)

    def test_une_date_anterieure_a_la_commande_est_refusee(self):
        """On ne peut pas avoir payé une commande avant qu'elle existe."""
        trop_tot = (timezone.localtime(self.commande.date_confirmation) - timedelta(days=1)).date()

        with self.assertRaises(ValueError) as erreur:
            self._verser("1000", date_paiement=trop_tot.isoformat())

        self.assertIn("précéder", str(erreur.exception))
        self.assertEqual(ReglementPaiement.objects.count(), 0)

    def test_une_date_illisible_est_refusee(self):
        with self.assertRaises(ValueError) as erreur:
            self._verser("1000", date_paiement="12 aout")

        self.assertIn("invalide", str(erreur.exception))

    def test_plusieurs_reglements_partiels_gardent_chacun_leur_date(self):
        j1 = timezone.localdate() - timedelta(days=20)
        j2 = timezone.localdate() - timedelta(days=10)
        j3 = timezone.localdate()

        self._verser("4000", date_paiement=j1.isoformat(), methode=MethodePaiement.ESPECES)
        self._verser("3000", date_paiement=j2.isoformat(), methode=MethodePaiement.VIREMENT_BANCAIRE)
        self._verser("3000", date_paiement=j3.isoformat(), methode=MethodePaiement.ORANGE_MONEY)

        reglements = list(ReglementPaiement.objects.all())
        self.assertEqual([r.date_paiement for r in reglements], [j1, j2, j3])
        self.assertEqual(
            [r.methode for r in reglements],
            [MethodePaiement.ESPECES, MethodePaiement.VIREMENT_BANCAIRE, MethodePaiement.ORANGE_MONEY],
        )
        self.commande.paiement.refresh_from_db()
        self.assertEqual(self.commande.paiement.montant_paye, Decimal("10000"))

    def test_le_virement_bancaire_est_un_moyen_accepte(self):
        self._verser("1000", methode=MethodePaiement.VIREMENT_BANCAIRE)

        self.assertEqual(ReglementPaiement.objects.get().methode, MethodePaiement.VIREMENT_BANCAIRE)

    def test_le_formulaire_propose_la_date_et_les_quatre_moyens(self):
        self.client.force_login(self.compta)

        page = self.client.get(reverse("paiements:modifier_paiement", args=[self.commande.pk])).content.decode()

        self.assertIn('name="date_paiement"', page)
        for libelle in ("Orange Money", "MTN Mobile Money", "Espèces (cash)", "Virement bancaire"):
            self.assertIn(libelle, page)

    def test_l_historique_affiche_les_deux_dates(self):
        self._verser("1000", date_paiement=(timezone.localdate() - timedelta(days=3)).isoformat())
        self.client.force_login(self.compta)

        page = self.client.get(reverse("paiements:modifier_paiement", args=[self.commande.pk])).content.decode()

        self.assertIn("Payé le", page)
        self.assertIn("Saisi le", page)
