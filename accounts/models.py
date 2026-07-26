from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = "admin", "Administrateur FRPS"
    FORMATION_SANITAIRE = "formation_sanitaire", "Formation sanitaire"
    PERSONNEL_STOCK = "personnel_stock", "Personnel FRPS - Gestion du stock"
    PERSONNEL_COMPTABILITE = "personnel_comptabilite", "Personnel FRPS - Édition des reçus"


class User(AbstractUser):
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.FORMATION_SANITAIRE)
    telephone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Numéro utilisé pour les notifications SMS (format international, ex: +237...)",
    )

    @property
    def is_formation_sanitaire(self):
        return self.role == Role.FORMATION_SANITAIRE

    @property
    def is_admin_frps(self):
        return self.role == Role.ADMIN

    @property
    def is_personnel_stock(self):
        return self.role == Role.PERSONNEL_STOCK

    @property
    def is_personnel_comptabilite(self):
        return self.role == Role.PERSONNEL_COMPTABILITE

    def __str__(self):
        return self.get_full_name() or self.username


class FormationSanitaire(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="formation_sanitaire")
    nom = models.CharField(max_length=255)
    region = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    adresse = models.CharField(max_length=255, blank=True)
    telephone_contact = models.CharField(max_length=20, blank=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Formation sanitaire"
        verbose_name_plural = "Formations sanitaires"
        ordering = ["nom"]

    def __str__(self):
        return self.nom
