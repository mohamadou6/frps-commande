from django.conf import settings
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

    # statut_envoi ci-dessus ne reflète que l'acceptation de la requête par la
    # passerelle (ex: Orange répond 201 même si le SMS n'est jamais livré, voir
    # notifications/backends.py). Les deux champs suivants portent le VRAI statut
    # de livraison, reçu de façon asynchrone via le callback Delivery Receipt (DR)
    # d'Orange (voir views.orange_dr_callback) — vides tant qu'aucun DR n'est reçu.
    reference_externe = models.CharField(
        max_length=100, blank=True, help_text="resource_id (Orange) ou SID (Twilio) renvoyé par la passerelle"
    )
    statut_livraison = models.CharField(
        max_length=32, blank=True, help_text="Statut brut reçu du callback DR (ex: DeliveredToTerminal, DeliveryImpossible)"
    )
    date_statut_livraison = models.DateTimeField(null=True, blank=True)

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


class PushSubscription(models.Model):
    """Abonnement Web Push d'un navigateur/appareil (PWA ou APK installé) pour un
    utilisateur : permet une notification instantanée si l'appareil est en ligne,
    livrée dès la reconnexion sinon (géré par le service de push, pas par nous)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    appareil_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "Identifiant stable du navigateur/appareil (tiré du localStorage). Sert à "
            "remplacer l'abonnement précédent du même appareil au lieu d'en accumuler un de plus."
        ),
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(
        auto_now=True,
        help_text="Dernier réenregistrement par l'appareil : au-delà de la péremption, l'abonnement est supprimé.",
    )
    date_dernier_envoi = models.DateTimeField(null=True, blank=True)
    dernier_statut = models.CharField(
        max_length=32,
        blank=True,
        help_text=(
            "Réponse du service de push au dernier envoi. « envoyé » signifie accepté, "
            "pas livré : c'est le test depuis l'appareil qui tranche."
        ),
    )

    class Meta:
        verbose_name = "Abonnement push"
        verbose_name_plural = "Abonnements push"

    def __str__(self):
        return f"Abonnement push de {self.user}"
