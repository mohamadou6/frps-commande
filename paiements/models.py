from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class StatutPaiement(models.TextChoices):
    EN_ATTENTE = "en_attente", "En attente"
    CONFIRME = "confirme", "Confirmé"
    ECHOUE = "echoue", "Échoué"


class MethodePaiement(models.TextChoices):
    ORANGE_MONEY = "orange_money", "Orange Money"
    MTN_MOMO = "mtn_momo", "MTN Mobile Money"
    ESPECES = "especes", "Espèces (cash)"
    VIREMENT_BANCAIRE = "virement_bancaire", "Virement bancaire"


class EtatPaiement(models.TextChoices):
    NON_PAYEE = "non_payee", "Non payée"
    PARTIELLE = "partielle", "Partiellement payée"
    PAYEE = "payee", "Payée intégralement"


class Paiement(models.Model):
    """Suivi du paiement effectué hors application (espèces remises au FRPS) — le
    paiement en ligne (Orange Money) reste en pause (voir CLAUDE.md). Le personnel
    comptabilité saisit ici le montant reçu après vérification, la FOSA le voit en
    lecture seule sur sa commande."""

    commande = models.OneToOneField("commandes.Commande", on_delete=models.CASCADE, related_name="paiement")
    methode = models.CharField(max_length=32, choices=MethodePaiement.choices, default=MethodePaiement.ORANGE_MONEY)
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    statut = models.CharField(max_length=16, choices=StatutPaiement.choices, default=StatutPaiement.EN_ATTENTE)
    reference_transaction = models.CharField(max_length=100, blank=True)
    date_initiation = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)

    montant_paye = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    date_maj_paiement = models.DateTimeField(null=True, blank=True)
    maj_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-date_initiation"]

    def __str__(self):
        return f"Paiement {self.get_methode_display()} - commande #{self.commande_id} ({self.get_statut_display()})"

    @property
    def etat(self):
        if self.montant_paye <= 0:
            return EtatPaiement.NON_PAYEE
        if self.montant_paye < self.commande.montant_total:
            return EtatPaiement.PARTIELLE
        return EtatPaiement.PAYEE


class ReglementPaiement(models.Model):
    """Un versement individuel (espèces) reçu pour une commande, saisi par le
    personnel comptabilité. Paiement.montant_paye reste le cumul de ces
    versements — cette table est l'historique qui permet de le justifier."""

    paiement = models.ForeignKey(Paiement, on_delete=models.CASCADE, related_name="reglements")
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    methode = models.CharField(max_length=32, choices=MethodePaiement.choices, default=MethodePaiement.ESPECES)

    # Deux dates volontairement distinctes : une FOSA peut régler un jour et la saisie
    # n'être faite que plus tard. date_paiement porte la réalité comptable (saisie à la
    # main, c'est elle qui fait foi), date_reglement l'horodatage technique de la saisie
    # — non modifiable, il sert de piste d'audit.
    date_paiement = models.DateField(
        default=timezone.localdate,
        help_text="Date à laquelle la FOSA a réellement réglé, qui peut précéder la saisie.",
    )
    date_reglement = models.DateTimeField(auto_now_add=True, help_text="Horodatage de la saisie dans l'application.")
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "Règlement"
        verbose_name_plural = "Règlements"
        ordering = ["date_paiement", "date_reglement"]

    def __str__(self):
        return f"{self.montant} FCFA - commande #{self.paiement.commande_id} ({self.date_paiement:%d/%m/%Y})"
