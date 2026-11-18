import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from commandes import services as commandes_services
from notifications.models import SMSLog

from . import services
from .models import MotifReclamation, PhotoReclamation, Reclamation, StatutReclamation


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class ReclamationTests(TestCase):
    def setUp(self):
        self.stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Plainte", telephone_contact="699000002")
        autre_user = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        self.autre = FormationSanitaire.objects.create(user=autre_user, nom="CSI Autre")
        produit = Produit.objects.create(code_sage="R1", nom="Amox", prix_unitaire=Decimal("100"), stock_disponible=20)
        panier = commandes_services.get_panier(self.fosa)
        commandes_services.ajouter_produit(panier, produit, 2)
        self.commande = commandes_services.confirmer_commande(panier)

    def _creer(self, **kwargs):
        donnees = {"motif": MotifReclamation.PRODUIT_MANQUANT, "description": "2 boites manquantes"}
        donnees.update(kwargs)
        self.client.force_login(self.fosa.user)
        return self.client.post(reverse("reclamations:nouvelle"), donnees)

    # --- Création par la FOSA ---

    def test_la_fosa_cree_une_reclamation_sur_sa_commande(self):
        reponse = self._creer(commande=self.commande.pk)
        reclamation = Reclamation.objects.get()
        self.assertRedirects(reponse, reverse("reclamations:detail", args=[reclamation.pk]))
        self.assertEqual(reclamation.commande, self.commande)
        self.assertEqual(reclamation.statut, StatutReclamation.OUVERTE)
        self.assertTrue(reclamation.non_lue_frps)

    def test_sans_commande_precise_c_est_accepte(self):
        self._creer(motif=MotifReclamation.RETARD)
        self.assertIsNone(Reclamation.objects.get().commande)

    def test_description_vide_refusee(self):
        self._creer(description="   ")
        self.assertFalse(Reclamation.objects.exists())

    def test_motif_inconnu_refuse(self):
        self._creer(motif="n_importe_quoi")
        self.assertFalse(Reclamation.objects.exists())

    def test_la_commande_d_une_autre_fosa_est_refusee(self):
        self.client.force_login(self.autre.user)
        self.client.post(
            reverse("reclamations:nouvelle"),
            {"motif": MotifReclamation.QUANTITE, "description": "x", "commande": self.commande.pk},
        )
        self.assertFalse(Reclamation.objects.exists())

    def test_le_personnel_ne_cree_pas_de_reclamation(self):
        self.client.force_login(self.stock)
        self.client.post(reverse("reclamations:nouvelle"), {"motif": MotifReclamation.AUTRE, "description": "x"})
        self.assertFalse(Reclamation.objects.exists())

    # --- Visibilité ---

    def test_une_fosa_ne_voit_pas_les_reclamations_d_une_autre(self):
        self._creer()
        reclamation = Reclamation.objects.get()
        self.client.force_login(self.autre.user)
        self.assertEqual(self.client.get(reverse("reclamations:detail", args=[reclamation.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("reclamations:liste")), "CSI Plainte")
        reponse = self.client.post(reverse("reclamations:repondre", args=[reclamation.pk]), {"texte": "intrus"})
        self.assertEqual(reponse.status_code, 404)

    def test_le_personnel_voit_toutes_les_reclamations_a_traiter(self):
        self._creer()
        self.client.force_login(self.stock)
        reponse = self.client.get(reverse("reclamations:liste"))
        self.assertContains(reponse, "CSI Plainte")

    def test_non_connecte_renvoye_a_la_connexion(self):
        reponse = self.client.get(reverse("reclamations:liste"))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse("login"), reponse.url)

    # --- Échanges et statut ---

    def test_reponse_du_frps_visible_et_signalee_a_la_fosa(self):
        self._creer()
        reclamation = Reclamation.objects.get()
        self.client.force_login(self.stock)
        self.client.get(reverse("reclamations:detail", args=[reclamation.pk]))
        self.client.post(
            reverse("reclamations:repondre", args=[reclamation.pk]),
            {"texte": "Nous livrons demain", "statut": StatutReclamation.EN_COURS},
        )
        reclamation.refresh_from_db()
        self.assertFalse(reclamation.non_lue_frps)
        self.assertTrue(reclamation.non_lue_fosa)
        self.assertEqual(reclamation.statut, StatutReclamation.EN_COURS)
        self.assertEqual(reclamation.traitee_par, self.stock)

        self.client.force_login(self.fosa.user)
        self.assertEqual(self.client.get(reverse("catalogue:liste")).context["reclamations_non_lues_count"], 1)
        self.assertContains(self.client.get(reverse("reclamations:detail", args=[reclamation.pk])), "Nous livrons demain")
        reclamation.refresh_from_db()
        self.assertFalse(reclamation.non_lue_fosa)

    def test_resolution_previent_la_fosa_par_sms(self):
        self._creer()
        reclamation = Reclamation.objects.get()
        services.reponse_frps(reclamation, self.stock, "Avoir établi", statut=StatutReclamation.RESOLUE)
        reclamation.refresh_from_db()
        self.assertIsNotNone(reclamation.date_resolution)
        sms = SMSLog.objects.get(type_evenement="reclamation_resolue")
        self.assertEqual(sms.destinataire, "+237699000002")
        self.assertLessEqual(len(sms.message), 160)

    def test_reponse_vide_sans_changement_refusee(self):
        self._creer()
        reclamation = Reclamation.objects.get()
        with self.assertRaises(ValueError):
            services.reponse_frps(reclamation, self.stock, "", statut=StatutReclamation.OUVERTE)

    def test_un_message_de_la_fosa_rouvre_une_reclamation_resolue(self):
        self._creer()
        reclamation = Reclamation.objects.get()
        services.reponse_frps(reclamation, self.stock, statut=StatutReclamation.RESOLUE)
        services.message_fosa(reclamation, self.fosa.user, "Toujours pas reçu")
        reclamation.refresh_from_db()
        self.assertEqual(reclamation.statut, StatutReclamation.OUVERTE)
        self.assertIsNone(reclamation.date_resolution)
        self.assertTrue(reclamation.non_lue_frps)

    def test_la_fosa_ne_peut_pas_changer_le_statut(self):
        self._creer()
        reclamation = Reclamation.objects.get()
        self.client.post(
            reverse("reclamations:repondre", args=[reclamation.pk]),
            {"texte": "c'est réglé", "statut": StatutReclamation.RESOLUE},
        )
        reclamation.refresh_from_db()
        self.assertEqual(reclamation.statut, StatutReclamation.OUVERTE)

    def test_supprimer_la_commande_garde_la_reclamation(self):
        self._creer(commande=self.commande.pk)
        commandes_services.supprimer_commande(self.commande)
        self.assertIsNone(Reclamation.objects.get().commande)


def _photo(nom="photo.png", taille=(2400, 1800), format_="PNG", mode="RGB"):
    from PIL import Image

    contenu = io.BytesIO()
    Image.new(mode, taille, "red" if mode == "RGB" else (255, 0, 0, 128)).save(contenu, format_)
    return SimpleUploadedFile(nom, contenu.getvalue(), content_type=f"image/{format_.lower()}")


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class PhotosReclamationTests(TestCase):
    def setUp(self):
        self.stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Photo")
        autre_user = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        self.autre = FormationSanitaire.objects.create(user=autre_user, nom="CSI Autre")
        self.client.force_login(fosa_user)

    def _creer(self, photos):
        return self.client.post(
            reverse("reclamations:nouvelle"),
            {"motif": MotifReclamation.ABIME_PERIME, "description": "Carton mouillé", "photos": photos},
        )

    def test_photos_jointes_a_la_creation_et_reduites(self):
        from PIL import Image

        self._creer([_photo(), _photo("b.png", (800, 600))])
        reclamation = Reclamation.objects.get()
        photos = list(reclamation.photos.order_by("pk"))
        self.assertEqual(len(photos), 2)
        self.assertIsNone(photos[0].message)
        self.assertEqual((photos[0].largeur, photos[0].hauteur), (1600, 1200))
        self.assertEqual((photos[1].largeur, photos[1].hauteur), (800, 600))
        self.assertEqual(Image.open(io.BytesIO(bytes(photos[0].contenu))).format, "JPEG")

    def test_png_transparent_converti_sur_fond_blanc(self):
        self._creer([_photo("t.png", (100, 100), "PNG", "RGBA")])
        self.assertEqual(PhotoReclamation.objects.count(), 1)

    def test_un_faux_fichier_image_est_refuse_sans_rien_creer(self):
        faux = SimpleUploadedFile("virus.jpg", b"MZ pas une image", content_type="image/jpeg")
        reponse = self._creer([faux])
        self.assertFalse(Reclamation.objects.exists())
        self.assertContains(reponse, "pas une image lisible")

    def test_plus_de_trois_photos_refusees(self):
        self._creer([_photo(f"{i}.png", (50, 50)) for i in range(4)])
        self.assertFalse(Reclamation.objects.exists())

    def test_message_avec_photo_seule_accepte(self):
        self._creer([])
        reclamation = Reclamation.objects.get()
        self.client.post(reverse("reclamations:repondre", args=[reclamation.pk]), {"texte": "", "photos": [_photo()]})
        message = reclamation.messages.get()
        self.assertEqual(message.photos.count(), 1)

    def test_le_frps_peut_joindre_une_photo(self):
        self._creer([])
        reclamation = Reclamation.objects.get()
        services.reponse_frps(reclamation, self.stock, "", photos=[_photo()])
        self.assertEqual(reclamation.messages.get().photos.count(), 1)

    def test_photo_servie_au_proprietaire_et_au_personnel_seulement(self):
        self._creer([_photo()])
        photo = PhotoReclamation.objects.get()
        url = reverse("reclamations:photo", args=[photo.pk])

        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse["Content-Type"], "image/jpeg")
        self.assertIn("private", reponse["Cache-Control"])

        self.client.force_login(self.stock)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.autre.user)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_la_page_affiche_les_vignettes(self):
        self._creer([_photo()])
        reclamation = Reclamation.objects.get()
        photo = reclamation.photos.get()
        reponse = self.client.get(reverse("reclamations:detail", args=[reclamation.pk]))
        self.assertContains(reponse, reverse("reclamations:photo", args=[photo.pk]))
        self.assertContains(reponse, 'enctype="multipart/form-data"')
