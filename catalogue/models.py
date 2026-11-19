from django.db import models


# Seuils d'alerte affichés sur les cartes du catalogue. Volontairement arbitraires
# (le stock va de quelques unités à plus d'un million selon les produits) : à ajuster
# si le terrain montre qu'ils déclenchent trop tôt ou trop tard.
SEUIL_STOCK_CRITIQUE = 10
SEUIL_STOCK_FAIBLE = 50


class Magasin(models.TextChoices):
    PRINCIPAL = "principal", "Magasin principal"
    UCPC = "ucpc", "Magasin UCPC"
    AUTRE = "autre", "Autre magasin (non affiché dans le catalogue)"


class Rayon(models.Model):
    """Rayon de classification du catalogue (ex. Injectables, Comprimés).
    Peuplé/rattaché aux produits via la commande import_rayons, depuis
    catalogue/data/rayons_classification.csv.
    """

    slug = models.SlugField(max_length=64, unique=True)
    nom = models.CharField(max_length=100)
    icone = models.CharField(max_length=8, blank=True, help_text="Emoji affiché à côté du nom du rayon")
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Rayon"
        verbose_name_plural = "Rayons"
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom


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
    rayon = models.ForeignKey(
        Rayon, on_delete=models.SET_NULL, null=True, blank=True, related_name="produits"
    )

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.stock_disponible} en stock)"

    @property
    def en_stock(self):
        return self.actif and self.stock_disponible > 0

    @property
    def niveau_stock(self):
        """« critique » / « faible » / « normal » : sans cette distinction, un produit
        à 2 unités s'affichait avec le même badge vert qu'un produit à 160 000, et la
        FOSA ne voyait pas qu'elle commandait sur un stock presque épuisé."""
        if self.stock_disponible <= 0:
            return "rupture"
        if self.stock_disponible < SEUIL_STOCK_CRITIQUE:
            return "critique"
        if self.stock_disponible < SEUIL_STOCK_FAIBLE:
            return "faible"
        return "normal"


# Promotions : une baisse du prix de vente reste mise en avant auprès des FOSA pendant
# cette durée, tant que le prix ne remonte pas. En dessous du seuil, ce n'est qu'un
# arrondi ou une correction de saisie, pas une promotion.
PROMOTION_DUREE_JOURS = 30
PROMOTION_SEUIL_POURCENT = 1


class BaissePrix(models.Model):
    """Trace d'une baisse du prix de vente, enregistrée à l'import Excel, dans l'admin
    ou par update_stock (catalogue/services.py noter_baisses_prix). C'est elle qui
    alimente le menu Promotions des FOSA."""

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="baisses_prix")
    ancien_prix = models.DecimalField(max_digits=12, decimal_places=2)
    nouveau_prix = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True, db_index=True)
    visible = models.BooleanField(
        "Affichée aux FOSA", default=True, help_text="Décocher pour retirer cette baisse du menu Promotions"
    )

    class Meta:
        verbose_name = "Baisse de prix (promotion)"
        verbose_name_plural = "Baisses de prix (promotions)"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.produit.nom} : {self.ancien_prix} → {self.nouveau_prix}"


class Promotion(models.Model):
    """Prix promotionnel décidé par l'admin FRPS pour une période. Pendant la période,
    c'est ce prix que la FOSA paie (catalogue/services.py prix_de_vente) : il est
    figé dans la ligne de commande à l'ajout au panier, comme tout prix."""

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="promotions")
    prix_promotionnel = models.DecimalField(max_digits=12, decimal_places=2)
    date_debut = models.DateField()
    date_fin = models.DateField(help_text="Dernier jour inclus")
    message = models.CharField(
        max_length=150, blank=True, help_text="Facultatif, affiché aux FOSA. Ex. : Offre de fin d'année"
    )
    active = models.BooleanField(default=True, help_text="Décocher pour arrêter la promotion avant sa fin")
    creee_par = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Promotion"
        verbose_name_plural = "Promotions"
        ordering = ["-date_debut", "produit__nom"]

    def __str__(self):
        return f"{self.produit.nom} à {self.prix_promotionnel} FCFA ({self.date_debut} → {self.date_fin})"

    @property
    def pourcentage(self):
        if not self.produit.prix_unitaire:
            return 0
        return round((1 - self.prix_promotionnel / self.produit.prix_unitaire) * 100)


class AlerteStock(models.Model):
    """« Prévenez-moi quand c'est disponible » : une FOSA demande à être avertie du
    retour en stock d'un produit en rupture. Prévenue une seule fois (push + SMS
    groupés), puis l'alerte reste visible comme « disponible » dans sa page."""

    formation_sanitaire = models.ForeignKey(
        "accounts.FormationSanitaire", on_delete=models.CASCADE, related_name="alertes_stock"
    )
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="alertes_stock")
    date_demande = models.DateTimeField(auto_now_add=True)
    date_notification = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Alerte de retour en stock"
        verbose_name_plural = "Alertes de retour en stock"
        unique_together = ("formation_sanitaire", "produit")
        ordering = ["-date_demande"]

    def __str__(self):
        return f"{self.formation_sanitaire.nom} attend {self.produit.nom}"


class ProduitHabituel(models.Model):
    """« Mes produits habituels » : liste personnelle d'une FOSA, avec la quantité
    qu'elle commande d'ordinaire. Sert aussi de modèle à la commande mensuelle."""

    formation_sanitaire = models.ForeignKey(
        "accounts.FormationSanitaire", on_delete=models.CASCADE, related_name="produits_habituels"
    )
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="habituels")
    quantite = models.PositiveIntegerField(default=1)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Produit habituel"
        verbose_name_plural = "Produits habituels"
        unique_together = ("formation_sanitaire", "produit")
        ordering = ["produit__nom"]

    def __str__(self):
        return f"{self.formation_sanitaire.nom} : {self.produit.nom} x{self.quantite}"


class CommandeMensuelle(models.Model):
    """Commande programmée : chaque mois, à partir du jour choisi, le panier de la FOSA
    est préparé avec ses produits habituels. Elle n'a plus qu'à vérifier et valider :
    rien n'est jamais validé à sa place (le stock serait débité sans elle)."""

    formation_sanitaire = models.OneToOneField(
        "accounts.FormationSanitaire", on_delete=models.CASCADE, related_name="commande_mensuelle"
    )
    jour_du_mois = models.PositiveSmallIntegerField(default=1, help_text="De 1 à 28")
    active = models.BooleanField(default=True)
    # Premier jour du mois de la dernière préparation : une seule par mois.
    dernier_mois_prepare = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Commande mensuelle programmée"
        verbose_name_plural = "Commandes mensuelles programmées"

    def __str__(self):
        return f"{self.formation_sanitaire.nom} : le {self.jour_du_mois} de chaque mois"
