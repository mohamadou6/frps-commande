from django.db import models


class Magasin(models.TextChoices):
    PRINCIPAL = "principal", "Magasin principal"
    UCPC = "ucpc", "Magasin UCPC"
    AUTRE = "autre", "Autre magasin (non affiché dans le catalogue)"


class Produit(models.Model):
    """Catalogue saisi et maintenu manuellement par l'admin FRPS via l'admin Django
    (prix/stock consultés dans Sage par l'admin, saisis ici à la main — pas de
    synchro automatique, voir CLAUDE.md).
    """

    code_sage = models.CharField(max_length=64, unique=True, help_text="Code produit dans Sage Gescom")
    nom = models.CharField(max_length=255)
    unite = models.CharField(max_length=32, blank=True, help_text="Ex: boîte, flacon, comprimé")
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    stock_disponible = models.PositiveIntegerField(default=0)
    magasin = models.CharField(
        max_length=16,
        choices=Magasin.choices,
        default=Magasin.PRINCIPAL,
        help_text="Seuls les produits des magasins Principal et UCPC apparaissent dans le catalogue FOSA",
    )
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
