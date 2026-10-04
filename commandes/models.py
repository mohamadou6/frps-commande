from decimal import Decimal

from django.conf import settings
from django.db import models

from frps_project.formatage import arrondir_montant


class StatutCommande(models.TextChoices):
    BROUILLON = "brouillon", "Brouillon (panier)"
    CONFIRMEE = "confirmee", "Confirmée"
    PAYEE = "payee", "Payée"
    ANNULEE = "annulee", "Annulée"


class Commande(models.Model):
    formation_sanitaire = models.ForeignKey(
        "accounts.FormationSanitaire", on_delete=models.PROTECT, related_name="commandes"
    )
    statut = models.CharField(max_length=16, choices=StatutCommande.choices, default=StatutCommande.BROUILLON)
    montant_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    date_creation = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Commande #{self.pk} - {self.formation_sanitaire.nom} ({self.get_statut_display()})"

    def recalculer_montant(self):
        # Les lignes gardent leurs décimales ; seul le total général est arrondi, et il
        # l'est ici, à l'enregistrement, pas seulement à l'affichage : le solde et l'état
        # de paiement se calculent ainsi sur le montant que tout le monde voit, et non
        # sur des centimes invisibles qui laissaient une commande réglée « partielle ».
        total = arrondir_montant(sum((ligne.sous_total for ligne in self.lignes.all()), Decimal("0")))
        self.montant_total = total
        self.save(update_fields=["montant_total"])
        return total

    @property
    def montant_paye(self):
        paiement = getattr(self, "paiement", None)
        return paiement.montant_paye if paiement else Decimal("0")

    @property
    def solde_restant(self):
        # Totaux et versements sont des FCFA entiers. Seul un règlement saisi avant
        # l'arrondi des totaux peut laisser un écart de centimes : il n'est pas
        # encaissable, et ne doit ni afficher un solde, ni bloquer l'état « payée ».
        solde = self.montant_total - self.montant_paye
        return solde if solde >= 1 else Decimal("0")

    @property
    def etat_paiement(self):
        paiement = getattr(self, "paiement", None)
        if paiement is None:
            from paiements.models import EtatPaiement

            return EtatPaiement.NON_PAYEE
        return paiement.etat


class LigneCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="lignes_commande")
    quantite = models.PositiveIntegerField()
    prix_unitaire_snapshot = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"
        unique_together = ("commande", "produit")

    def __str__(self):
        return f"{self.produit.nom} x{self.quantite}"

    @property
    def sous_total(self):
        if self.prix_unitaire_snapshot is None or self.quantite is None:
            return None
        return self.prix_unitaire_snapshot * self.quantite
