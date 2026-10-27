from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .forms import MESSAGE_FOSA_SANS_FICHE
from .models import FormationSanitaire, Role, User

MOT_DE_PASSE = "Tres-Secret-987"


class CompteFosaSansFicheTests(TestCase):
    """Un compte au rôle FOSA sans fiche FormationSanitaire faisait tomber toutes les
    pages en 500 dès sa connexion, y compris /login/ et /admin/login/ (prod, 2026-10-27)."""

    def setUp(self):
        self.compte = User.objects.create_user(
            username="fosa_sans_fiche", password=MOT_DE_PASSE, role=Role.FORMATION_SANITAIRE
        )

    def _messages(self, reponse):
        return [str(m) for m in get_messages(reponse.wsgi_request)]

    def test_connexion_refusee_avec_le_motif(self):
        reponse = self.client.post(reverse("login"), {"username": "fosa_sans_fiche", "password": MOT_DE_PASSE})

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "rattaché à aucune formation sanitaire")
        self.assertNotContains(reponse, "Identifiants incorrects")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_mauvais_mot_de_passe_garde_le_message_habituel(self):
        reponse = self.client.post(reverse("login"), {"username": "fosa_sans_fiche", "password": "faux"})

        self.assertContains(reponse, "Identifiants incorrects")

    def test_session_deja_ouverte_les_pages_communes_ne_plantent_plus(self):
        self.client.force_login(self.compte)

        for url in (reverse("login"), reverse("admin:login"), reverse("service_worker")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_session_deja_ouverte_deconnectee_avec_le_motif(self):
        for url in (reverse("catalogue:liste"), reverse("commandes:panier")):
            self.client.force_login(self.compte)

            reponse = self.client.get(url)

            self.assertRedirects(reponse, reverse("login"), fetch_redirect_response=False)
            self.assertNotIn("_auth_user_id", self.client.session)
            self.assertIn(MESSAGE_FOSA_SANS_FICHE, self._messages(reponse))

    def test_compte_fosa_avec_fiche_se_connecte(self):
        FormationSanitaire.objects.create(user=self.compte, nom="CSI de test")

        reponse = self.client.post(reverse("login"), {"username": "fosa_sans_fiche", "password": MOT_DE_PASSE})

        self.assertRedirects(reponse, reverse("catalogue:liste"), fetch_redirect_response=False)


class AdminCreationCompteTests(TestCase):
    def setUp(self):
        admin = User.objects.create_superuser("frps_admin", "admin@example.com", MOT_DE_PASSE, role=Role.ADMIN)
        self.client.force_login(admin)

    def _creer(self, role):
        return self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": f"nouveau_{role}",
                "usable_password": "true",
                "password1": MOT_DE_PASSE,
                "password2": MOT_DE_PASSE,
                "role": role,
                "telephone": "",
            },
            follow=True,
        )

    def test_compte_fosa_sans_fiche_signale(self):
        reponse = self._creer(Role.FORMATION_SANITAIRE)

        self.assertTrue(User.objects.filter(username="nouveau_formation_sanitaire").exists())
        self.assertTrue(any("aucune fiche" in str(m) for m in reponse.context["messages"]))

    def test_compte_personnel_pas_d_avertissement(self):
        reponse = self._creer(Role.PERSONNEL_STOCK)

        self.assertTrue(User.objects.filter(username="nouveau_personnel_stock").exists())
        self.assertFalse(any("aucune fiche" in str(m) for m in reponse.context["messages"]))
