from django.templatetags.static import static
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


class CommandeHorsConnexionPwaTests(TestCase):
    """Commande préparée sans réseau : envoyée par le service worker (Background Sync)
    ou par la page, via le même js/demandes.js. La logique serveur est testée dans
    commandes/tests.py (CommandeHorsConnexionTests)."""

    def test_le_service_worker_envoie_les_demandes_en_arriere_plan(self):
        sw = self.client.get(reverse("service_worker")).content.decode()

        self.assertIn(f'importScripts("{static("js/demandes.js")}");', sw)
        self.assertIn('self.addEventListener("sync"', sw)
        self.assertIn(f'const URL_DEMANDES = "{reverse("commandes:synchroniser_demande")}";', sw)
        # Le service worker garde sa règle : il n'intercepte jamais un envoi (POST),
        # il envoie lui-même des demandes que le serveur ne traite qu'une fois.
        self.assertIn('if (requete.method !== "GET") return;', sw)

    def test_le_module_des_demandes_est_mis_en_cache_a_l_installation(self):
        sw = self.client.get(reverse("service_worker")).content.decode()
        debut = sw.index("const RESSOURCES_COQUILLE")

        self.assertIn(f'"{static("js/demandes.js")}"', sw[debut:sw.index("];", debut)])

    def test_seule_une_fosa_porte_le_panneau_de_commande_hors_connexion(self):
        fosa = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        FormationSanitaire.objects.create(user=fosa, nom="CSI Test")
        stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)

        self.client.force_login(fosa)
        page_fosa = self.client.get(reverse("commandes:historique")).content.decode()
        self.client.force_login(stock)
        page_stock = self.client.get(reverse("notifications:liste")).content.decode()

        self.assertIn('id="commande-hors-ligne"', page_fosa)
        self.assertIn(f'data-compte="{fosa.pk}"', page_fosa)
        self.assertIn(static("js/demandes.js"), page_fosa)
        self.assertNotIn('id="commande-hors-ligne"', page_stock)
        self.assertNotIn(static("js/demandes.js"), page_stock)
