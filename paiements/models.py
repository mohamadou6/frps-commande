from django.db import models


class StatutPaiement(models.TextChoices):
    EN_ATTENTE = "en_attente", "En attente"
    CONFIRME = "confirme", "Confirmé"
    ECHOUE = "echoue", "Échoué"


class MethodePaiement(models.TextChoices):
    ORANGE_MONEY = "orange_money", "Orange Money"
    ESPECES = "especes", "Espèces (cash)"


class Paiement(models.Model):
    commande = models.OneToOneField("commandes.Commande", on_delete=models.CASCADE, related_name="paiement")
    methode = models.CharField(max_length=32, choices=MethodePaiement.choices, default=MethodePaiement.ORANGE_MONEY)
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    statut = models.CharField(max_length=16, choices=StatutPaiement.choices, default=StatutPaiement.EN_ATTENTE)
    reference_transaction = models.CharField(max_length=100, blank=True)
    date_initiation = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-date_initiation"]

    def __str__(self):
        return f"Paiement {self.get_methode_display()} - commande #{self.commande_id} ({self.get_statut_display()})"
