import io
import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import FormationSanitaire, Role, User
from commandes import services as commandes_services
from notifications.models import PushSubscription, SMSLog

from . import espace_fosa, recherche
from .models import AlerteStock, CommandeMensuelle, Produit, ProduitHabituel


def _classeur(lignes):
    wb = Workbook()
    ws = wb.active
    ws.append(["code_sage", "prix_unitaire", "stock_disponible"])
    for ligne in lignes:
        ws.append(list(ligne))
    contenu = io.BytesIO()
    wb.save(contenu)
    return SimpleUploadedFile("produits.xlsx", contenu.getvalue())


class RechercheTolerante(TestCase):
    """Mêmes règles que accounts/static/js/app.js : si l'un change, l'autre aussi."""

    def _trouve(self, requete, nom):
        return bool(recherche.filtrer([Produit(nom=nom)], requete))

    def test_accents_majuscules_et_mots_dans_le_desordre(self):
        self.assertTrue(self._trouve("PARACÉTAMOL 500", "Paracetamol 500mg comprimé"))
        self.assertTrue(self._trouve("500 para", "Paracetamol 500mg comprimé"))

    def test_lettres_doublees(self):
        self.assertTrue(self._trouve("amoxiciline", "Amoxicilline 500mg gélule"))

    def test_une_faute_toleree_des_5_lettres(self):
        self.assertTrue(self._trouve("paracetemol", "Paracetamol 500mg"))
        self.assertTrue(self._trouve("ibuprofne", "Ibuprofène 400mg"))
        self.assertFalse(self._trouve("paxacetemol", "Paracetamol 500mg"))  # deux fautes
        self.assertFalse(self._trouve("zinx", "Zinc 20mg"))  # mot court : pas de tolérance

    def test_les_chiffres_ne_sont_pas_fusionnes(self):
        self.assertFalse(self._trouve("10mg", "Paracetamol 100mg"))
        self.assertTrue(self._trouve("100mg", "Paracetamol 100mg"))

    def test_synonymes(self):
        self.assertTrue(self._trouve("acetaminophene", "Paracetamol 500mg"))
        self.assertTrue(self._trouve("aspirine", "Acide acétylsalicylique 100mg"))

    def test_les_synonymes_sont_transmis_au_telephone(self):
        self.assertIn("paracetamol", json.loads(recherche.synonymes_json()))


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class EspaceFosaBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_frps", password="x", role=Role.ADMIN)
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(
            user=fosa_user, nom="CSI Espace", district="Garoua 1", telephone_contact="699000003"
        )
        self.para = Produit.objects.create(code_sage="E1", nom="Paracetamol 500mg", prix_unitaire=Decimal("100"), stock_disponible=100)
        self.amox = Produit.objects.create(code_sage="E2", nom="Amoxicilline 500mg", prix_unitaire=Decimal("200"), stock_disponible=0)
        self.zinc = Produit.objects.create(code_sage="E3", nom="Zinc 20mg", prix_unitaire=Decimal("50"), stock_disponible=40)
        self.client.force_login(fosa_user)


class AlertesStockTests(EspaceFosaBase):
    def test_la_recherche_du_catalogue_propose_les_produits_en_rupture(self):
        page = self.client.get(reverse("catalogue:liste"), {"q": "amoxiciline"})
        self.assertEqual(page.context["ruptures"], [self.amox])
        self.assertContains(page, "🔔 M'alerter")

    def test_demander_puis_annuler_une_alerte(self):
        self.client.post(reverse("catalogue:demander_alerte", args=[self.amox.pk]))
        self.assertTrue(AlerteStock.objects.filter(formation_sanitaire=self.fosa, produit=self.amox).exists())
        self.client.post(reverse("catalogue:annuler_alerte", args=[self.amox.pk]))
        self.assertFalse(AlerteStock.objects.exists())

    def test_pas_d_alerte_sur_un_produit_disponible(self):
        self.client.post(reverse("catalogue:demander_alerte", args=[self.para.pk]))
        self.assertFalse(AlerteStock.objects.exists())

    @mock.patch("notifications.push.envoyer_push_aux_utilisateurs")
    def test_retour_en_stock_un_seul_sms_et_un_seul_push_par_fosa(self, push):
        zinc_rupture = Produit.objects.create(code_sage="E4", nom="Fer 200mg", prix_unitaire=Decimal("10"), stock_disponible=0)
        espace_fosa.demander_alerte(self.fosa, self.amox)
        espace_fosa.demander_alerte(self.fosa, zinc_rupture)
        Produit.objects.filter(pk__in=[self.amox.pk, zinc_rupture.pk]).update(stock_disponible=20)

        self.assertEqual(espace_fosa.traiter_retours_en_stock(), 2)
        sms = SMSLog.objects.get(type_evenement="retour_stock")
        self.assertEqual(sms.destinataire, "+237699000003")
        self.assertIn("Amoxicilline", sms.message)
        self.assertLessEqual(len(sms.message), 160)
        self.assertEqual(push.call_count, 1)
        # Deuxième passage : personne n'est prévenu deux fois.
        self.assertEqual(espace_fosa.traiter_retours_en_stock(), 0)
        self.assertEqual(SMSLog.objects.filter(type_evenement="retour_stock").count(), 1)

    def test_l_import_excel_declenche_les_alertes(self):
        espace_fosa.demander_alerte(self.fosa, self.amox)
        self.client.force_login(self.admin)
        self.client.post(reverse("catalogue:importer"), {"fichier": _classeur([("E2", 200, 15)])})
        self.assertIsNotNone(AlerteStock.objects.get().date_notification)

    def test_une_alerte_se_rearme_pour_le_retour_suivant(self):
        espace_fosa.demander_alerte(self.fosa, self.amox)
        Produit.objects.filter(pk=self.amox.pk).update(stock_disponible=5)
        espace_fosa.traiter_retours_en_stock()
        Produit.objects.filter(pk=self.amox.pk).update(stock_disponible=0)
        self.amox.refresh_from_db()
        espace_fosa.demander_alerte(self.fosa, self.amox)
        self.assertIsNone(AlerteStock.objects.get().date_notification)

    def test_reserve_aux_fosa_et_en_post(self):
        self.client.get(reverse("catalogue:demander_alerte", args=[self.amox.pk]))
        self.assertFalse(AlerteStock.objects.exists())
        stock = User.objects.create_user(username="stock", password="x", role=Role.PERSONNEL_STOCK)
        self.client.force_login(stock)
        self.client.post(reverse("catalogue:demander_alerte", args=[self.amox.pk]))
        self.assertFalse(AlerteStock.objects.exists())


class HabituelsTests(EspaceFosaBase):
    def test_etoile_ajoute_puis_retire(self):
        url = reverse("catalogue:basculer_habituel", args=[self.para.pk])
        self.client.post(url, {"suivant": "/catalogue/"})
        self.assertTrue(ProduitHabituel.objects.filter(formation_sanitaire=self.fosa, produit=self.para).exists())
        self.assertContains(self.client.get(reverse("catalogue:liste")), "⭐ Produit habituel")
        self.client.post(url)
        self.assertFalse(ProduitHabituel.objects.exists())

    def test_retour_vers_une_adresse_externe_refuse(self):
        reponse = self.client.post(reverse("catalogue:basculer_habituel", args=[self.para.pk]), {"suivant": "//exemple.com"})
        self.assertRedirects(reponse, reverse("catalogue:habituels"))

    def test_tout_mettre_au_panier_plafonne_et_ignore_les_ruptures(self):
        ProduitHabituel.objects.create(formation_sanitaire=self.fosa, produit=self.para, quantite=150)
        ProduitHabituel.objects.create(formation_sanitaire=self.fosa, produit=self.zinc, quantite=10)
        ProduitHabituel.objects.create(formation_sanitaire=self.fosa, produit=self.amox, quantite=5)
        self.client.post(reverse("catalogue:habituels"), {"action": "panier"})
        panier = commandes_services.get_panier(self.fosa)
        self.assertEqual(dict(panier.lignes.values_list("produit_id", "quantite")), {self.para.pk: 100, self.zinc.pk: 10})

    def test_modifier_les_quantites_et_retirer_avec_zero(self):
        ProduitHabituel.objects.create(formation_sanitaire=self.fosa, produit=self.para, quantite=1)
        ProduitHabituel.objects.create(formation_sanitaire=self.fosa, produit=self.zinc, quantite=1)
        self.client.post(
            reverse("catalogue:habituels"),
            {"action": "enregistrer", f"quantite_{self.para.pk}": "7", f"quantite_{self.zinc.pk}": "0"},
        )
        self.assertEqual(list(ProduitHabituel.objects.values_list("produit_id", "quantite")), [(self.para.pk, 7)])

    def test_preremplir_avec_les_produits_les_plus_commandes(self):
        for _ in range(2):
            panier = commandes_services.get_panier(self.fosa)
            commandes_services.ajouter_produit(panier, self.para, 4)
            commandes_services.confirmer_commande(panier)
        self.client.post(reverse("catalogue:preremplir_habituels"))
        self.assertEqual(ProduitHabituel.objects.get().quantite, 4)


class SuggestionsTests(EspaceFosaBase):
    def setUp(self):
        super().setUp()
        voisin_user = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        self.voisin = FormationSanitaire.objects.create(user=voisin_user, nom="CSI Voisin", district="Garoua 1")
        panier = commandes_services.get_panier(self.voisin)
        commandes_services.ajouter_produit(panier, self.para, 2)
        commandes_services.ajouter_produit(panier, self.zinc, 2)
        commandes_services.confirmer_commande(panier)

    def test_souvent_commande_avec_le_panier(self):
        produits = espace_fosa.suggestions(self.fosa, exclure_ids=[self.para.pk])
        self.assertEqual([p.pk for p in produits], [self.zinc.pk])
        self.assertIn("avec votre panier", produits[0].raison_suggestion)

    def test_populaire_dans_le_district_sans_panier(self):
        produits = espace_fosa.suggestions(self.fosa)
        self.assertEqual({p.pk for p in produits}, {self.para.pk, self.zinc.pk})
        self.assertIn("Garoua 1", produits[0].raison_suggestion)

    def test_jamais_un_produit_en_rupture(self):
        Produit.objects.filter(pk=self.zinc.pk).update(stock_disponible=0)
        self.assertNotIn(self.zinc.pk, [p.pk for p in espace_fosa.suggestions(self.fosa)])

    def test_affichees_sur_la_page_du_panier(self):
        page = self.client.get(reverse("commandes:panier"))
        self.assertContains(page, "Vous pourriez aussi avoir besoin de")


class CommandeMensuelleTests(EspaceFosaBase):
    def setUp(self):
        super().setUp()
        ProduitHabituel.objects.create(formation_sanitaire=self.fosa, produit=self.para, quantite=3)

    def test_jour_hors_bornes_refuse(self):
        with self.assertRaises(ValueError):
            espace_fosa.programmer_commande_mensuelle(self.fosa, 31)

    def test_preparee_une_seule_fois_par_mois_a_partir_du_jour(self):
        espace_fosa.programmer_commande_mensuelle(self.fosa, 10)
        self.assertIsNone(espace_fosa.preparer_si_echue(self.fosa, date(2026, 12, 9)))
        self.assertIsNotNone(espace_fosa.preparer_si_echue(self.fosa, date(2026, 12, 12)))
        self.assertIsNone(espace_fosa.preparer_si_echue(self.fosa, date(2026, 12, 20)))
        self.assertIsNotNone(espace_fosa.preparer_si_echue(self.fosa, date(2027, 1, 10)))
        self.assertEqual(commandes_services.get_panier(self.fosa).lignes.get().quantite, 6)

    def test_jamais_validee_a_la_place_de_la_fosa(self):
        espace_fosa.programmer_commande_mensuelle(self.fosa, 1)
        espace_fosa.preparer_si_echue(self.fosa)
        self.assertEqual(self.fosa.commandes.exclude(statut="brouillon").count(), 0)

    def test_preparee_a_la_visite_avec_un_message(self):
        espace_fosa.programmer_commande_mensuelle(self.fosa, 1)
        page = self.client.get(reverse("catalogue:liste"), follow=True)
        self.assertIn("commande du mois est prête", " ".join(str(m) for m in page.context["messages"]))
        self.assertIsNotNone(CommandeMensuelle.objects.get().dernier_mois_prepare)

    def test_desactivee_rien_ne_se_passe(self):
        espace_fosa.programmer_commande_mensuelle(self.fosa, 1, active=False)
        self.assertIsNone(espace_fosa.preparer_si_echue(self.fosa))


@override_settings(VAPID_PUBLIC_KEY="cle-publique-test")
class PushFosaTests(EspaceFosaBase):
    def test_la_fosa_recoit_la_cle_et_le_bandeau(self):
        page = self.client.get(reverse("catalogue:liste"))
        self.assertEqual(page.context["vapid_public_key"], "cle-publique-test")
        self.assertContains(page, "quand votre commande est prête")

    def test_la_fosa_peut_enregistrer_un_appareil(self):
        corps = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}, "appareil_id": "tel-1"}
        reponse = self.client.post(reverse("notifications:abonnement_push"), json.dumps(corps), content_type="application/json")
        self.assertEqual(reponse.status_code, 204)
        self.assertEqual(PushSubscription.objects.get().user, self.fosa.user)

    def test_compte_fosa_sans_fiche_refuse(self):
        sans_fiche = User.objects.create_user(username="orphelin", password="x", role=Role.FORMATION_SANITAIRE)
        self.client.force_login(sans_fiche)
        corps = {"endpoint": "https://push.example/z", "keys": {"p256dh": "x", "auth": "y"}}
        reponse = self.client.post(reverse("notifications:abonnement_push"), json.dumps(corps), content_type="application/json")
        self.assertEqual(reponse.status_code, 403)

    @mock.patch("notifications.push.envoyer_push_aux_utilisateurs")
    def test_push_a_la_fosa_quand_sa_commande_est_prete(self, push):
        from commandes.models import EtapeTraitement

        panier = commandes_services.get_panier(self.fosa)
        commandes_services.ajouter_produit(panier, self.para, 1)
        commande = commandes_services.confirmer_commande(panier)
        commandes_services.avancer_etape(commande, EtapeTraitement.EN_PREPARATION)
        push.reset_mock()
        commandes_services.avancer_etape(commande, EtapeTraitement.PRETE)
        destinataires, titre = push.call_args.args[0], push.call_args.args[1]
        self.assertEqual(list(destinataires), [self.fosa.user_id])
        self.assertIn("prête", titre)


class UpdateStockTests(EspaceFosaBase):
    """Régression : la commande plantait (imports manquants) dès qu'un prix baissait."""

    def test_baisse_et_retour_en_stock_par_la_commande(self):
        espace_fosa.demander_alerte(self.fosa, self.amox)
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "maj.csv"
            chemin.write_text("code_sage;nom;prix_unitaire;stock_disponible\nE1;Paracetamol;80;100\nE2;Amox;200;12\n", encoding="utf-8")
            call_command("update_stock", file=str(chemin), stdout=io.StringIO())
        self.para.refresh_from_db()
        self.assertEqual(self.para.prix_unitaire, Decimal("80"))
        self.assertTrue(self.para.baisses_prix.exists())
        self.assertIsNotNone(AlerteStock.objects.get().date_notification)
