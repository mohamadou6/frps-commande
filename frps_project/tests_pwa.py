from django.test import TestCase
from django.urls import reverse

from accounts.models import FormationSanitaire, Role, User


class HorsConnexionTests(TestCase):
    """Comportement sans réseau : servi par le service worker, vérifié ici sur le
    contenu rendu par Django (le service worker lui-même tourne dans le navigateur)."""

    def test_louverture_hors_ligne_retombe_sur_la_page_daccueil_du_compte(self):
        """L'icône de l'écran d'accueil ouvre « / », une simple redirection jamais
        mise en cache : sans ce repli, l'app installée affichait « Pas de connexion »."""
        sw = self.client.get(reverse("service_worker")).content.decode()

        self.assertIn(f'const PAGES_ACCUEIL = ["{reverse("catalogue:liste")}", "{reverse("statistiques:index")}"]', sw)
        self.assertIn("marquerHorsLigne(accueil)", sw)

    def test_une_page_resservie_depuis_le_cache_est_marquee(self):
        sw = self.client.get(reverse("service_worker")).content.decode()

        self.assertIn("return marquerHorsLigne(enCache);", sw)
        self.assertIn('data-hors-ligne="1"', sw)

    def test_la_page_pas_de_connexion_liste_les_pages_enregistrees(self):
        page = self.client.get(reverse("hors_ligne")).content.decode()

        self.assertIn('id="liste-pages"', page)
        self.assertIn('id="bouton-retour"', page)

    def test_les_pages_portent_le_bandeau_hors_connexion(self):
        utilisateur = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        FormationSanitaire.objects.create(user=utilisateur, nom="CSI Test")
        self.client.force_login(utilisateur)

        page = self.client.get(reverse("commandes:panier")).content.decode()

        self.assertIn('id="bandeau-hors-ligne"', page)
