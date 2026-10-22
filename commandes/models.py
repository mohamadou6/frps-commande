from decimal import Decimal

from django.conf import settings
from django.db import models

from frps_project.formatage import arrondir_montant


class StatutCommande(models.TextChoices):
    BROUILLON = "brouillon", "Brouillon (panier)"
    CONFIRMEE = "confirmee", "Confirmée"
    PAYEE = "payee", "Payée"
    ANNULEE = "annulee", "Annulée"
    # Commande préparée sans réseau sur le téléphone de la FOSA, reçue par le serveur
    # mais pas encore validée (stock non débité). Normalement transitoire : la
    # validation suit la réception dans la même requête. Elle ne persiste que si la
    # validation a échoué, et le renvoi automatique du téléphone la reprend.
    EN_ATTENTE_SYNCHRO = "attente_synchro", "En attente de validation"


class Commande(models.Model):
    formation_sanitaire = models.ForeignKey(
        "accounts.FormationSanitaire", on_delete=models.PROTECT, related_name="commandes"
    )
    statut = models.CharField(max_length=16, choices=StatutCommande.choices, default=StatutCommande.BROUILLON)
    montant_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    date_creation = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)
    # Identifiant tiré par le téléphone pour une commande préparée hors connexion.
    # Le téléphone renvoie la même demande tant qu'il n'a pas reçu de réponse (réseau
    # coupé pendant l'envoi, envoi doublé par le service worker et la page) : ce champ
    # unique fait qu'un renvoi retrouve la commande déjà créée au lieu d'en créer une
    # seconde et de débiter le stock deux fois. Vide pour une commande passée en ligne.
    uuid_client = models.UUIDField(null=True, blank=True, unique=True, editable=False)

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
    def preparee_hors_ligne(self):
        return self.uuid_client is not None

    @property
    def est_effective(self):
        """Commande qui a débité le stock : la seule qui ait un bon (PDF) et un paiement."""
        return self.statut in (StatutCommande.CONFIRMEE, StatutCommande.PAYEE)

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


class LigneCommandeQuerySet(models.QuerySet):
    def servies(self):
        """Lignes réellement servies. Une demande hors connexion garde, à quantité 0,
        les produits que le stock n'a pas permis de servir : la FOSA doit les voir, mais
        ils n'ont rien à faire dans le bon de commande, les SMS ni les statistiques."""
        return self.filter(quantite__gt=0)


class LigneCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="lignes_commande")
    # Quantité servie : c'est elle qui a été débitée du stock et qui est facturée.
    quantite = models.PositiveIntegerField()
    prix_unitaire_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    # Quantité demandée hors connexion. Le stock a pu baisser entre la préparation sur
    # le téléphone et l'arrivée de la demande : le serveur sert alors ce qui reste
    # (`quantite`, éventuellement 0). Vide pour une commande passée en ligne, où
    # demandé = servi.
    quantite_demandee = models.PositiveIntegerField(null=True, blank=True)

    objects = LigneCommandeQuerySet.as_manager()

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"
        unique_together = ("commande", "produit")

    def __str__(self):
        return f"{self.produit.nom} x{self.quantite}"

    @property
    def servie_en_partie(self):
        """Vrai si le serveur a servi moins que ce que la FOSA avait demandé hors connexion."""
        return self.quantite_demandee is not None and self.quantite < self.quantite_demandee

    @property
    def sous_total(self):
        if self.prix_unitaire_snapshot is None or self.quantite is None:
            return None
        return self.prix_unitaire_snapshot * self.quantite
