import io
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commandes_services
from reclamations import services as reclamations_services
from reclamations.models import MotifReclamation, StatutReclamation
from statistiques.rapports import destinataires_rapport

from .emails import destinataires_personnel_frps
from .models import DestinataireEmail, EmailLog


def _photo():
    from PIL import Image

    contenu = io.BytesIO()
    Image.new("RGB", (300, 200), "blue").save(contenu, "PNG")
    return SimpleUploadedFile("p.png", contenu.getvalue(), content_type="image/png")


class PageParametresEmailsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        self.client.force_login(self.admin)
        self.url = reverse("notifications:parametres_emails")

    def test_ajouter_une_adresse_avec_ses_envois(self):
        self.client.post(self.url, {"email": " Qualite@FRPSno.com ", "nom": "Qualité", "envois": ["recoit_reclamations", "recoit_rapports"]})
        d = DestinataireEmail.objects.get()
        self.assertEqual(d.email, "qualite@frpsno.com")
        self.assertEqual((d.recoit_reclamations, d.recoit_commandes, d.recoit_rapports), (True, False, True))

    def test_adresse_invalide_ou_sans_envoi_refusee(self):
        self.client.post(self.url, {"email": "pas-une-adresse", "envois": ["recoit_reclamations"]})
        self.client.post(self.url, {"email": "ok@frpsno.com"})
        self.assertFalse(DestinataireEmail.objects.exists())

    def test_doublon_refuse(self):
        DestinataireEmail.objects.create(email="a@frpsno.com")
        reponse = self.client.post(self.url, {"email": "A@frpsno.com", "envois": ["recoit_commandes"]})
        self.assertEqual(DestinataireEmail.objects.count(), 1)
        self.assertContains(reponse, "déjà dans la liste")

    def test_modifier_desactiver_supprimer(self):
        d = DestinataireEmail.objects.create(email="a@frpsno.com")
        self.client.post(reverse("notifications:modifier_destinataire_email", args=[d.pk]), {"envois": ["recoit_commandes"]})
        d.refresh_from_db()
        self.assertEqual((d.actif, d.recoit_reclamations, d.recoit_commandes), (False, False, True))
        self.client.post(reverse("notifications:supprimer_destinataire_email", args=[d.pk]))
        self.assertFalse(DestinataireEmail.objects.exists())

    def test_email_de_test(self):
        d = DestinataireEmail.objects.create(email="a@frpsno.com")
        self.client.post(reverse("notifications:tester_destinataire_email", args=[d.pk]))
        self.assertEqual(mail.outbox[0].to, ["a@frpsno.com"])
        self.assertEqual(EmailLog.objects.get().type_evenement, "email_test")

    def test_mode_test_signale_quand_les_emails_ne_partent_pas(self):
        DestinataireEmail.objects.create(email="a@frpsno.com")
        reponse = self.client.post(
            reverse("notifications:tester_destinataire_email", args=[DestinataireEmail.objects.get().pk]), follow=True
        )
        self.assertContains(reponse, "Mode test")
        self.assertContains(reponse, "Simulé")
        self.assertNotContains(reponse, ">Envoyé<")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_pas_de_bandeau_quand_l_envoi_est_reel(self):
        self.assertNotContains(self.client.get(self.url), "Mode test")

    def test_reserve_a_l_admin(self):
        stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        d = DestinataireEmail.objects.create(email="a@frpsno.com")
        self.client.force_login(stock)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"email": "b@frpsno.com", "envois": ["recoit_commandes"]}).status_code, 403)
        self.assertEqual(self.client.post(reverse("notifications:supprimer_destinataire_email", args=[d.pk])).status_code, 403)
        self.assertTrue(DestinataireEmail.objects.filter(pk=d.pk).exists())

    def test_un_simple_get_ne_supprime_rien(self):
        d = DestinataireEmail.objects.create(email="a@frpsno.com")
        self.client.get(reverse("notifications:supprimer_destinataire_email", args=[d.pk]))
        self.assertTrue(DestinataireEmail.objects.filter(pk=d.pk).exists())

    def test_le_menu_parametres_n_apparait_que_pour_l_admin(self):
        self.assertContains(self.client.get(reverse("statistiques:index")), self.url)
        stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        self.client.force_login(stock)
        self.assertNotContains(self.client.get(reverse("statistiques:index")), self.url)


class ListesDeDestinatairesTests(TestCase):
    """Les adresses paramétrées s'ajoutent aux comptes pour les commandes et le rapport ;
    pour les réclamations, ce sont les seules."""

    def setUp(self):
        User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK, email="stock@frpsno.com")
        User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN, email="admin@frpsno.com")
        DestinataireEmail.objects.create(email="commandes@frpsno.com", recoit_commandes=True, recoit_reclamations=False)
        DestinataireEmail.objects.create(email="rapport@frpsno.com", recoit_rapports=True, recoit_reclamations=False)
        DestinataireEmail.objects.create(email="eteint@frpsno.com", actif=False, recoit_commandes=True, recoit_rapports=True)
        DestinataireEmail.objects.create(email="STOCK@frpsno.com", recoit_commandes=True)  # doublon d'un compte

    def test_commandes_comptes_plus_liste_sans_doublon_ni_inactif(self):
        self.assertEqual(
            destinataires_personnel_frps(), ["admin@frpsno.com", "commandes@frpsno.com", "stock@frpsno.com"]
        )

    def test_rapport_admin_plus_liste(self):
        self.assertEqual(destinataires_rapport(), ["admin@frpsno.com", "rapport@frpsno.com"])


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log", PUBLIC_BASE_URL="https://frpsno.com")
class EmailReclamationTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK, email="stock@frpsno.com")
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Mail", district="Garoua 2")
        produit = Produit.objects.create(code_sage="M1", nom="Amox", prix_unitaire=Decimal("100"), stock_disponible=10)
        panier = commandes_services.get_panier(self.fosa)
        commandes_services.ajouter_produit(panier, produit, 1)
        self.commande = commandes_services.confirmer_commande(panier)
        mail.outbox.clear()

    def _creer(self, photos=None):
        return reclamations_services.creer_reclamation(
            self.fosa, self.fosa.user, MotifReclamation.ABIME_PERIME, "Flacons cassés", self.commande, photos=photos
        )

    def test_email_aux_seules_adresses_reclamations_avec_photos_et_lien(self):
        DestinataireEmail.objects.create(email="qualite@frpsno.com")
        DestinataireEmail.objects.create(email="eteint@frpsno.com", actif=False)
        reclamation = self._creer(photos=[_photo()])

        self.assertEqual([m.to for m in mail.outbox], [["qualite@frpsno.com"]])  # pas le compte stock
        message = mail.outbox[0]
        self.assertIn(f"#{reclamation.pk}", message.subject)
        self.assertIn("CSI Mail", message.subject)
        self.assertIn("Flacons cassés", message.body)
        self.assertIn(f"https://frpsno.com/reclamations/{reclamation.pk}/", message.body)
        self.assertIn(f"#{self.commande.pk}", message.body)
        self.assertEqual(len(message.attachments), 1)
        log = EmailLog.objects.get(type_evenement="reclamation")
        self.assertEqual(log.commande, self.commande)

    def test_sans_adresse_rien_ne_part_et_la_reclamation_est_creee(self):
        with self.assertLogs("notifications.emails", "WARNING"):
            reclamation = self._creer()
        self.assertEqual(mail.outbox, [])
        self.assertTrue(reclamation.pk)

    def test_un_relais_en_panne_n_empeche_pas_la_reclamation(self):
        DestinataireEmail.objects.create(email="qualite@frpsno.com")
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="127.0.0.1", EMAIL_PORT=1):
            reclamation = self._creer()
        self.assertTrue(reclamation.pk)
        self.assertEqual(EmailLog.objects.get(type_evenement="reclamation").statut_envoi, "echec")

    def test_email_a_la_reouverture_seulement(self):
        DestinataireEmail.objects.create(email="qualite@frpsno.com")
        reclamation = self._creer()
        stock = User.objects.get(username="stock")
        mail.outbox.clear()

        reclamations_services.message_fosa(reclamation, self.fosa.user, "Une précision")
        self.assertEqual(mail.outbox, [])

        reclamations_services.reponse_frps(reclamation, stock, statut=StatutReclamation.RESOLUE)
        reclamations_services.message_fosa(reclamation, self.fosa.user, "Toujours cassés")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("rouverte", mail.outbox[0].subject)
        self.assertIn("Toujours cassés", mail.outbox[0].body)

    def test_rappel_sur_la_page_des_reclamations_pour_l_admin(self):
        admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse("reclamations:liste")), "Aucune adresse ne reçoit")
        DestinataireEmail.objects.create(email="qualite@frpsno.com")
        self.assertNotContains(self.client.get(reverse("reclamations:liste")), "Aucune adresse ne reçoit")
