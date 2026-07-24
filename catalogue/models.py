from django.db import models


class Produit(models.Model):
    """Cache local du catalogue Sage Gescom. Source de vérité = SQL Server FRPS.

    Ce tableau est réécrit par `stock_sync` (management command `sync_stock`) ;
    ne pas modifier le stock manuellement ici.
    """

    code_sage = models.CharField(max_length=64, unique=True, help_text="Code produit dans Sage Gescom")
    nom = models.CharField(max_length=255)
    unite = models.CharField(max_length=32, blank=True, help_text="Ex: boîte, flacon, comprimé")
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    stock_disponible = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True, help_text="Désactivé automatiquement si absent du dernier import")
    derniere_synchro = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.stock_disponible} en stock)"

    @property
    def en_stock(self):
        return self.actif and self.stock_disponible > 0
