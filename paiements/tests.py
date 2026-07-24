from decimal import Decimal

from django.test import TestCase, override_settings

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commande_services
from notifications.models import SMSLog, WhatsAppLog

from . import services
from .models import MethodePaiement, StatutPaiement


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
