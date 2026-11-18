from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import FormationSanitaire, Role, User
from catalogue.models import Produit
from paiements.models import Paiement

from . import services
from .models import Commande, EtapeTraitement, LigneCommande


@override_settings(SMS_BACKEND="log", WHATSAPP_BACKEND="log")
class RechercheHistoriqueTests(TestCase):
    """Recherche dans « Mes commandes » : par numéro, période, montant, produit, étape,
    paiement, avec tri et résumé."""

    def setUp(self):
        fosa_user = User.objects.create_user(username="csi1", password="x", role=Role.FORMATION_SANITAIRE)
        self.fosa = FormationSanitaire.objects.create(user=fosa_user, nom="CSI Recherche")
        self.para = Produit.objects.create(code_sage="R1", nom="Paracetamol", prix_unitaire=Decimal("100"), stock_disponible=1000)
        self.amox = Produit.objects.create(code_sage="R2", nom="Amoxicilline", prix_unitaire=Decimal("1000"), stock_disponible=1000)
        self.petite = self._commande(self.para, 5)  # 500 FCFA
        self.grosse = self._commande(self.amox, 10)  # 10 000 FCFA
        Commande.objects.filter(pk=self.petite.pk).update(date_creation=timezone.now() - timedelta(days=40))
        autre_user = User.objects.create_user(username="csi2", password="x", role=Role.FORMATION_SANITAIRE)
        self.autre = FormationSanitaire.objects.create(user=autre_user, nom="CSI Autre")
        self.commande_autre = self._commande(self.para, 1, self.autre)
        self.client.force_login(fosa_user)

    def _commande(self, produit, quantite, fosa=None):
        panier = services.get_panier(fosa or self.fosa)
        services.ajouter_produit(panier, produit, quantite)
        return services.confirmer_commande(panier)

    def _ids(self, **params):
        reponse = self.client.get(reverse("commandes:historique"), params)
        return [c.pk for c in reponse.context["commandes"]]

    def test_sans_critere_toutes_mes_commandes_les_recentes_d_abord(self):
        self.assertEqual(self._ids(), [self.grosse.pk, self.petite.pk])

    def test_jamais_les_commandes_d_une_autre_fosa(self):
        self.assertNotIn(self.commande_autre.pk, self._ids(numero=self.commande_autre.pk))

    def test_par_numero_avec_ou_sans_diese(self):
        self.assertEqual(self._ids(numero=f"#{self.petite.pk}"), [self.petite.pk])

    def test_par_periode(self):
        self.assertEqual(self._ids(debut=(timezone.localdate() - timedelta(days=7)).isoformat()), [self.grosse.pk])
        self.assertEqual(self._ids(fin=(timezone.localdate() - timedelta(days=7)).isoformat()), [self.petite.pk])

    def test_par_montant_avec_espaces(self):
        self.assertEqual(self._ids(montant_min="1 000"), [self.grosse.pk])
        self.assertEqual(self._ids(montant_max="1000"), [self.petite.pk])

    def test_par_produit_servi_seulement(self):
        self.assertEqual(self._ids(produit="amox"), [self.grosse.pk])
        LigneCommande.objects.create(
            commande=self.petite, produit=self.amox, quantite=0, quantite_demandee=3, prix_unitaire_snapshot=Decimal("1000")
        )
        self.assertEqual(self._ids(produit="amox"), [self.grosse.pk])

    def test_par_etape(self):
        Commande.objects.filter(pk=self.petite.pk).update(etape=EtapeTraitement.LIVREE)
        self.assertEqual(self._ids(etape="livree"), [self.petite.pk])

    def test_par_paiement(self):
        Paiement.objects.create(commande=self.grosse, montant=self.grosse.montant_total, montant_paye=Decimal("10000"))
        Paiement.objects.create(commande=self.petite, montant=self.petite.montant_total, montant_paye=Decimal("200"))
        self.assertEqual(self._ids(paiement="payee"), [self.grosse.pk])
        self.assertEqual(self._ids(paiement="partielle"), [self.petite.pk])
        Paiement.objects.filter(commande=self.petite).delete()
        self.assertEqual(self._ids(paiement="non_payee"), [self.petite.pk])

    def test_tri_par_montant(self):
        self.assertEqual(self._ids(tri="montant_asc"), [self.petite.pk, self.grosse.pk])

    def test_resume_nombre_et_total(self):
        reponse = self.client.get(reverse("commandes:historique"), {"produit": "a"})
        self.assertEqual(reponse.context["resume"], {"nombre": 2, "montant": Decimal("10500")})

    def test_critere_illisible_signale_sans_vider_la_liste(self):
        reponse = self.client.get(reverse("commandes:historique"), {"montant_min": "abc"}, follow=True)
        self.assertEqual(len(reponse.context["commandes"]), 2)
        self.assertIn("Montant illisible", " ".join(str(m) for m in reponse.context["messages"]))

    def test_aucun_resultat_message_adapte(self):
        self.assertContains(self.client.get(reverse("commandes:historique"), {"produit": "zzz"}), "Aucune commande ne correspond")

    def test_pagination_garde_les_criteres(self):
        for _ in range(26):
            self._commande(self.para, 1)
        reponse = self.client.get(reverse("commandes:historique"), {"produit": "para"})
        self.assertContains(reponse, "produit=para&page=2")
