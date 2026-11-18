from django.conf import settings
from django.db import models
from django.utils import timezone


class MotifReclamation(models.TextChoices):
    PRODUIT_MANQUANT = "produit_manquant", "Produit manquant à la livraison"
    QUANTITE = "quantite", "Quantité incorrecte"
    MAUVAIS_PRODUIT = "mauvais_produit", "Mauvais produit livré"
    ABIME_PERIME = "abime_perime", "Produit abîmé ou périmé"
    RETARD = "retard", "Retard de livraison"
    FACTURATION = "facturation", "Facturation ou paiement"
    AUTRE = "autre", "Autre"


class StatutReclamation(models.TextChoices):
    OUVERTE = "ouverte", "Ouverte"
    EN_COURS = "en_cours", "En cours de traitement"
    RESOLUE = "resolue", "Résolue"


class Reclamation(models.Model):
    formation_sanitaire = models.ForeignKey(
        "accounts.FormationSanitaire", on_delete=models.PROTECT, related_name="reclamations"
    )
    # Facultative : un retard ou une question de facturation ne vise pas toujours une
    # commande précise. SET_NULL : supprimer une commande saisie par erreur ne doit pas
    # effacer la réclamation qui en parlait.
    commande = models.ForeignKey(
        "commandes.Commande", on_delete=models.SET_NULL, null=True, blank=True, related_name="reclamations"
    )
    motif = models.CharField(max_length=32, choices=MotifReclamation.choices)
    description = models.TextField()
    statut = models.CharField(max_length=16, choices=StatutReclamation.choices, default=StatutReclamation.OUVERTE)
    traitee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    # Dernier message ou changement de statut : trie la liste par activité.
    date_activite = models.DateTimeField(default=timezone.now)
    date_resolution = models.DateTimeField(null=True, blank=True)
    # Pastilles « nouveau » : un message de la FOSA pas encore lu par le FRPS, et
    # inversement. Un simple drapeau suffit : un seul interlocuteur de chaque côté.
    non_lue_frps = models.BooleanField(default=True)
    non_lue_fosa = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Réclamation"
        verbose_name_plural = "Réclamations"
        ordering = ["-date_activite"]

    def __str__(self):
        return f"Réclamation #{self.pk} - {self.formation_sanitaire.nom} ({self.get_motif_display()})"

    @property
    def est_close(self):
        return self.statut == StatutReclamation.RESOLUE


class MessageReclamation(models.Model):
    reclamation = models.ForeignKey(Reclamation, on_delete=models.CASCADE, related_name="messages")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    de_la_fosa = models.BooleanField()
    texte = models.TextField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message de réclamation"
        verbose_name_plural = "Messages de réclamation"
        ordering = ["date"]

    def __str__(self):
        return f"Message #{self.pk} sur la réclamation #{self.reclamation_id}"


class PhotoReclamation(models.Model):
    """Photo jointe à une réclamation (produit abîmé, colis ouvert, bon de livraison…).

    Stockée en base et non sur disque : le disque d'un service Render est effacé à
    chaque déploiement, et la base est sauvegardée. Elle est réduite à l'arrivée
    (services.preparer_photo), ~150 Ko, ce qui garde la base légère."""

    reclamation = models.ForeignKey(Reclamation, on_delete=models.CASCADE, related_name="photos")
    # Vide : photo jointe à la description initiale. Sinon : au message qui l'a portée.
    message = models.ForeignKey(
        MessageReclamation, on_delete=models.CASCADE, null=True, blank=True, related_name="photos"
    )
    contenu = models.BinaryField()
    largeur = models.PositiveIntegerField()
    hauteur = models.PositiveIntegerField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Photo de réclamation"
        verbose_name_plural = "Photos de réclamation"
        ordering = ["pk"]

    def __str__(self):
        return f"Photo #{self.pk} de la réclamation #{self.reclamation_id}"

    @property
    def taille_ko(self):
        return round(len(self.contenu) / 1024)

