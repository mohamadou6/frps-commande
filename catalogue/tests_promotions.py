import io
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from accounts.models import FormationSanitaire, Role, User
from commandes import services as commandes_services

from . import services
from .models import BaissePrix, Produit, Promotion


def _jour(decalage=0):
    return timezone.localdate() + timedelta(days=decalage)


def _classeur(lignes):
    wb = Workbook()
    ws = wb.active
    ws.append(["code_sage", "prix_unitaire", "stock_disponible"])
    for ligne in lignes:
        ws.append(list(ligne))
    contenu = io.BytesIO()
    wb.save(contenu)
    return SimpleUploadedFile("produits.xlsx", contenu.getvalue())


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class PromotionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Promo")
        self.produit = Produit.objects.create(
            code_sage="P1", nom="Paracetamol", prix_unitaire=Decimal("1000"), stock_disponible=100
        )

    def _promo(self, prix="800", debut=0, fin=10, **kwargs):
        return services.creer_promotion(self.produit, prix, _jour(debut), _jour(fin), auteur=self.admin, **kwargs)

    # --- Prix appliqué ---

    def test_le_prix_promotionnel_est_paye_pendant_la_promotion(self):
        self._promo()
        panier = commandes_services.get_panier(self.fosa)
        commandes_services.ajouter_produit(panier, self.produit, 2)
        commande = commandes_services.confirmer_commande(panier)
        ligne = commande.lignes.get()
        self.assertEqual(ligne.prix_unitaire_snapshot, Decimal("800"))
        commande.refresh_from_db()
        self.assertEqual(commande.montant_total, Decimal("1600"))

    def test_prix_normal_avant_et_apres_la_periode(self):
        self._promo(debut=2, fin=5)
        self.assertEqual(services.prix_de_vente(self.produit), Decimal("1000"))
        Promotion.objects.update(date_debut=_jour(-10), date_fin=_jour(-1))
        self.assertEqual(services.prix_de_vente(self.produit), Decimal("1000"))

    def test_le_dernier_jour_est_inclus(self):
        self._promo(debut=-3, fin=0)
        self.assertEqual(services.prix_de_vente(self.produit), Decimal("800"))

    def test_promotion_arretee_rend_le_prix_normal(self):
        promo = self._promo()
        services.arreter_promotion(promo)
        self.assertEqual(services.prix_de_vente(self.produit), Decimal("1000"))

    def test_commande_hors_connexion_au_prix_promotionnel(self):
        self._promo()
        commande, _ = commandes_services.synchroniser_demande(self.fosa, uuid.uuid4(), {self.produit.pk: 3})
        self.assertEqual(commande.lignes.get().prix_unitaire_snapshot, Decimal("800"))

    def test_si_le_prix_normal_passe_sous_la_promo_le_plus_bas_s_applique(self):
        self._promo(prix="800")
        Produit.objects.filter(pk=self.produit.pk).update(prix_unitaire=Decimal("700"))
        self.produit.refresh_from_db()
        self.assertEqual(services.prix_de_vente(self.produit), Decimal("700"))
        self.assertFalse(services.promotions_en_cours().exists())

    # --- Règles de saisie ---

    def test_prix_superieur_ou_egal_au_prix_normal_refuse(self):
        with self.assertRaises(ValueError):
            self._promo(prix="1000")

    def test_periode_passee_ou_inversee_refusee(self):
        with self.assertRaises(ValueError):
            self._promo(debut=-5, fin=-1)
        with self.assertRaises(ValueError):
            self._promo(debut=5, fin=2)

    def test_deux_promotions_qui_se_chevauchent_refusees(self):
        self._promo(debut=0, fin=10)
        with self.assertRaises(ValueError):
            self._promo(prix="700", debut=5, fin=15)
        self._promo(prix="700", debut=11, fin=15)  # à la suite : accepté
        self.assertEqual(Promotion.objects.count(), 2)

    # --- Pages ---

    def test_la_fosa_voit_la_promotion_et_le_bandeau_du_catalogue(self):
        self._promo(message="Offre de fin d'année")
        self.client.force_login(self.fosa.user)
        page = self.client.get(reverse("catalogue:promotions"))
        self.assertContains(page, "Paracetamol")
        self.assertContains(page, "Offre de fin d")
        self.assertContains(page, "-20 %")
        catalogue = self.client.get(reverse("catalogue:liste"))
        self.assertContains(catalogue, "1 produit en promotion")
        self.assertContains(catalogue, 'data-produit-prix="800.00"')

    def test_produit_en_rupture_absent_des_promotions(self):
        self._promo()
        Produit.objects.filter(pk=self.produit.pk).update(stock_disponible=0)
        self.client.force_login(self.fosa.user)
        self.assertNotContains(self.client.get(reverse("catalogue:promotions")), "Paracetamol")

    def test_l_admin_cree_et_arrete_une_promotion_depuis_l_application(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("catalogue:gerer_promotions"),
            {"produit": self.produit.pk, "prix": "750", "debut": _jour().isoformat(), "fin": _jour(7).isoformat()},
        )
        promo = Promotion.objects.get()
        self.assertEqual((promo.prix_promotionnel, promo.creee_par), (Decimal("750"), self.admin))
        self.client.post(reverse("catalogue:arreter_promotion", args=[promo.pk]))
        promo.refresh_from_db()
        self.assertFalse(promo.active)

    def test_gestion_reservee_a_l_admin(self):
        stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        promo = self._promo()
        for user in (stock, self.fosa.user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("catalogue:gerer_promotions")).status_code, 403)
            self.assertEqual(self.client.post(reverse("catalogue:arreter_promotion", args=[promo.pk])).status_code, 403)
        promo.refresh_from_db()
        self.assertTrue(promo.active)

    def test_compteur_du_menu(self):
        self._promo()
        self.client.force_login(self.fosa.user)
        self.assertEqual(self.client.get(reverse("commandes:historique")).context["nb_promotions_menu"], 1)


class BaissePrixTests(TestCase):
    """Baisses durables du prix de vente : détectées seules, signalées à part des promotions."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Info")
        self.produit = Produit.objects.create(
            code_sage="B1", nom="Amoxicilline", prix_unitaire=Decimal("1000"), stock_disponible=50
        )

    def test_import_excel_enregistre_les_baisses_seulement(self):
        Produit.objects.create(code_sage="B2", nom="Zinc", prix_unitaire=Decimal("100"), stock_disponible=5)
        self.client.force_login(self.admin)
        self.client.post(reverse("catalogue:importer"), {"fichier": _classeur([("B1", 900, 50), ("B2", 120, 5)])})
        baisse = BaissePrix.objects.get()
        self.assertEqual((baisse.produit, baisse.ancien_prix, baisse.nouveau_prix), (self.produit, Decimal("1000"), Decimal("900")))
        self.assertFalse(Promotion.objects.exists())  # une baisse n'est pas une promotion

    def test_baisse_infime_ignoree(self):
        self.assertEqual(services.noter_baisses_prix([(self.produit, Decimal("1000"), Decimal("995"))]), 0)

    def test_baisse_dans_l_admin_django_enregistree(self):
        self.client.force_login(User.objects.create_superuser(username="root", password="x", role=Role.ADMIN))
        url = reverse("admin:catalogue_produit_change", args=[self.produit.pk])
        donnees = {
            "code_sage": "B1", "nom": "Amoxicilline", "unite": "", "prix_unitaire": "850",
            "stock_disponible": "50", "magasin": "principal", "actif": "on", "rayon": "",
        }
        self.client.post(url, donnees)
        self.assertEqual(BaissePrix.objects.get().nouveau_prix, Decimal("850"))

    def test_la_baisse_est_un_type_de_promotion(self):
        services.noter_baisses_prix([(self.produit, Decimal("1250"), Decimal("1000"))])
        self.client.force_login(self.fosa.user)
        page = self.client.get(reverse("catalogue:promotions"))
        self.assertContains(page, "Amoxicilline")
        self.assertContains(page, "Prix en baisse -20 %")
        self.assertEqual(page.context["nb_baisses"], 1)
        self.assertNotContains(self.client.get(reverse("catalogue:promotions"), {"type": "offre"}), "Amoxicilline")
        self.assertContains(self.client.get(reverse("catalogue:promotions"), {"type": "baisse"}), "Amoxicilline")

    def test_produit_en_offre_speciale_pas_repete_dans_les_baisses(self):
        services.noter_baisses_prix([(self.produit, Decimal("1250"), Decimal("1000"))])
        services.creer_promotion(self.produit, "800", timezone.localdate(), timezone.localdate(), auteur=self.admin)
        offres, baisses = services.toutes_les_promotions()
        self.assertEqual(([p.produit_id for p in offres], baisses), ([self.produit.pk], []))
        self.assertEqual(services.nombre_promotions(), 1)

    def test_compteur_du_menu_compte_les_deux_types(self):
        autre = Produit.objects.create(code_sage="B9", nom="Zinc", prix_unitaire=Decimal("100"), stock_disponible=5)
        services.noter_baisses_prix([(self.produit, Decimal("1250"), Decimal("1000"))])
        services.creer_promotion(autre, "80", timezone.localdate(), timezone.localdate(), auteur=self.admin)
        self.client.force_login(self.fosa.user)
        self.assertEqual(self.client.get(reverse("commandes:historique")).context["nb_promotions_menu"], 2)
        self.assertContains(self.client.get(reverse("catalogue:liste")), "2 produits en promotion")

    def test_prix_remonte_plus_signale(self):
        services.noter_baisses_prix([(self.produit, Decimal("1250"), Decimal("1000"))])
        Produit.objects.filter(pk=self.produit.pk).update(prix_unitaire=Decimal("1100"))
        self.assertEqual(services.baisses_prix_recentes(), [])

    def test_baisse_ancienne_plus_signalee(self):
        services.noter_baisses_prix([(self.produit, Decimal("1250"), Decimal("1000"))])
        BaissePrix.objects.update(date=timezone.now() - timedelta(days=services.BAISSE_DUREE_JOURS + 1))
        self.assertEqual(services.baisses_prix_recentes(), [])

    def test_l_admin_masque_une_baisse(self):
        services.noter_baisses_prix([(self.produit, Decimal("1250"), Decimal("1000"))])
        self.client.force_login(self.admin)
        self.client.post(reverse("catalogue:masquer_baisse", args=[self.produit.pk]))
        self.assertEqual(services.baisses_prix_recentes(), [])
        self.client.force_login(self.fosa.user)
        self.assertEqual(self.client.post(reverse("catalogue:masquer_baisse", args=[self.produit.pk])).status_code, 403)
