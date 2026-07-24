from django.db import models


class TypeEvenement(models.TextChoices):
    NOUVELLE_COMMANDE = "nouvelle_commande", "Nouvelle commande"
    PAIEMENT_CONFIRME = "paiement_confirme", "Paiement confirmé"


class StatutEnvoi(models.TextChoices):
    ENVOYE = "envoye", "Envoyé"
    ECHEC = "echec", "Échec"


class SMSLog(models.Model):
    destinataire = models.CharField(max_length=20)
    message = models.TextField()
    type_evenement = models.CharField(max_length=32, choices=TypeEvenement.choices)
    statut_envoi = models.CharField(max_length=16, choices=StatutEnvoi.choices)
    commande = models.ForeignKey(
        "commandes.Commande", on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_envoyes"
    )
    date_envoi = models.DateTimeField(auto_now_add=True)
    detail_erreur = models.TextField(blank=True)

    class Meta:
        verbose_name = "SMS envoyé"
        verbose_name_plural = "SMS envoyés"
        ordering = ["-date_envoi"]

    def __str__(self):
        return f"{self.get_type_evenement_display()} -> {self.destinataire} ({self.get_statut_envoi_display()})"


class WhatsAppLog(models.Model):
    """Envoi du PDF de la commande validée vers les numéros WhatsApp configurés."""

    destinataire = models.CharField(max_length=20)
    commande = models.ForeignKey(
        "commandes.Commande", on_delete=models.SET_NULL, null=True, blank=True, related_name="whatsapp_envoyes"
    )
    statut_envoi = models.CharField(max_length=16, choices=StatutEnvoi.choices)
    date_envoi = models.DateTimeField(auto_now_add=True)
    detail_erreur = models.TextField(blank=True)

    class Meta:
        verbose_name = "Envoi WhatsApp"
        verbose_name_plural = "Envois WhatsApp"
        ordering = ["-date_envoi"]

    def __str__(self):
        return f"PDF commande #{self.commande_id} -> {self.destinataire} ({self.get_statut_envoi_display()})"


class Notification(models.Model):
    """Notification interne à l'application, gratuite et immédiate pour le
    personnel FRPS connecté — en complément du SMS (payant, dépendant du réseau)."""

    role_cible = models.CharField(max_length=32, help_text="Rôle destinataire (accounts.Role)")
    type_evenement = models.CharField(max_length=32, choices=TypeEvenement.choices)
    message = models.TextField()
    commande = models.ForeignKey(
        "commandes.Commande", on_delete=models.CASCADE, related_name="notifications_internes"
    )
    lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification interne"
        verbose_name_plural = "Notifications internes"
        ordering = ["-date_creation"]

    def __str__(self):
        return self.message
