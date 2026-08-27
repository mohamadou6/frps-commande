import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commande_services
from paiements import services as paiement_services

from .models import Notification, PushSubscription
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


@override_settings(VAPID_PRIVATE_KEY="cle-privee-de-test", VAPID_CLAIMS_EMAIL="mailto:test@frpsno.com")
class AbonnementPushTests(TestCase):
    """Un jeton d'abonnement tourne régulièrement côté navigateur. Sans ménage, la base
    accumulait un abonnement fantôme par rotation : accepté par FCM (201) mais ne livrant
    plus rien, si bien qu'une commande validée n'arrivait que sur un seul appareil."""

    def setUp(self):
        self.stock = User.objects.create_user(username="stock-push", password="x", role=Role.PERSONNEL_STOCK)
        self.autre = User.objects.create_user(username="autre-push", password="x", role=Role.PERSONNEL_STOCK)
        self.client.force_login(self.stock)

    def _abonner(self, endpoint, appareil_id="", ancien_endpoint=""):
        corps = {"endpoint": endpoint, "keys": {"p256dh": "cle-p256dh", "auth": "cle-auth"}}
        if appareil_id:
            corps["appareil_id"] = appareil_id
        if ancien_endpoint:
            corps["ancien_endpoint"] = ancien_endpoint
        return self.client.post(
            reverse("notifications:abonnement_push"), data=json.dumps(corps), content_type="application/json"
        )

    def test_le_meme_appareil_remplace_son_abonnement_au_lieu_den_ajouter_un(self):
        self._abonner("https://fcm.example/jeton-1", appareil_id="appareil-A")

        self._abonner("https://fcm.example/jeton-2", appareil_id="appareil-A")

        endpoints = list(PushSubscription.objects.values_list("endpoint", flat=True))
        self.assertEqual(endpoints, ["https://fcm.example/jeton-2"])

    def test_deux_appareils_distincts_gardent_chacun_leur_abonnement(self):
        self._abonner("https://fcm.example/telephone", appareil_id="appareil-A")
        self._abonner("https://fcm.example/ordinateur", appareil_id="appareil-B")

        self.assertEqual(PushSubscription.objects.count(), 2)

    def test_rotation_du_jeton_par_le_service_worker_supprime_lancien_endpoint(self):
        """Le service worker n'a pas accès au localStorage : il identifie l'abonnement
        remplacé par l'endpoint précédent (event.oldSubscription)."""
        self._abonner("https://fcm.example/jeton-1")

        self._abonner("https://fcm.example/jeton-2", ancien_endpoint="https://fcm.example/jeton-1")

        endpoints = list(PushSubscription.objects.values_list("endpoint", flat=True))
        self.assertEqual(endpoints, ["https://fcm.example/jeton-2"])

    def test_le_service_worker_nefface_pas_lappareil_id_deja_connu(self):
        self._abonner("https://fcm.example/jeton-1", appareil_id="appareil-A")

        self._abonner("https://fcm.example/jeton-1")

        self.assertEqual(PushSubscription.objects.get().appareil_id, "appareil-A")

    def test_abonnement_jamais_reconfirme_supprime_sans_envoi(self):
        from .push import _PEREMPTION_JOURS, envoyer_push_a_utilisateur

        self._abonner("https://fcm.example/fantome", appareil_id="appareil-A")
        self._abonner("https://fcm.example/vivant", appareil_id="appareil-B")
        PushSubscription.objects.filter(endpoint="https://fcm.example/fantome").update(
            date_confirmation=timezone.now() - timedelta(days=_PEREMPTION_JOURS + 1)
        )

        with patch("notifications.push.webpush") as envoi, patch("notifications.push._vapid"):
            envoyer_push_a_utilisateur(self.stock, "Titre", "Corps")

        envoyes = [appel.kwargs["subscription_info"]["endpoint"] for appel in envoi.call_args_list]
        self.assertEqual(envoyes, ["https://fcm.example/vivant"])
        self.assertFalse(PushSubscription.objects.filter(endpoint="https://fcm.example/fantome").exists())

    def test_bouton_tester_nenvoie_qua_lappareil_choisi(self):
        self._abonner("https://fcm.example/telephone", appareil_id="appareil-A")
        self._abonner("https://fcm.example/ordinateur", appareil_id="appareil-B")
        cible = PushSubscription.objects.get(endpoint="https://fcm.example/ordinateur")

        with patch("notifications.push.webpush") as envoi, patch("notifications.push._vapid"):
            reponse = self.client.post(reverse("notifications:tester_abonnement_push", args=[cible.pk]))

        self.assertEqual(envoi.call_count, 1)
        self.assertEqual(
            envoi.call_args.kwargs["subscription_info"]["endpoint"], "https://fcm.example/ordinateur"
        )
        self.assertEqual(reponse.status_code, 302)

    def test_on_ne_peut_ni_tester_ni_supprimer_lappareil_dun_autre(self):
        abonnement_autre = PushSubscription.objects.create(
            user=self.autre, endpoint="https://fcm.example/autre", p256dh="cle", auth="auth"
        )

        test = self.client.post(reverse("notifications:tester_abonnement_push", args=[abonnement_autre.pk]))
        suppression = self.client.post(
            reverse("notifications:supprimer_abonnement_push", args=[abonnement_autre.pk])
        )

        self.assertEqual(test.status_code, 404)
        self.assertEqual(suppression.status_code, 404)
        self.assertTrue(PushSubscription.objects.filter(pk=abonnement_autre.pk).exists())

    def test_la_page_notifications_liste_les_appareils_de_lutilisateur(self):
        self._abonner("https://fcm.example/telephone", appareil_id="appareil-A")
        PushSubscription.objects.create(
            user=self.autre, endpoint="https://fcm.example/autre", p256dh="cle", auth="auth"
        )

        reponse = self.client.get(reverse("notifications:liste"))

        self.assertEqual([a.endpoint for a in reponse.context["abonnements_push"]], ["https://fcm.example/telephone"])
