"""
Stock : journal de mouvements immuable + solde matérialisé.

Principe directeur, imposé par la section 10 du cahier des charges
(« toute correction se fait par mouvement compensatoire tracé, jamais par
écrasement ») : MouvementStock est une table en ajout seul. On ne modifie ni
ne supprime jamais une ligne. La quantité en stock est la somme des mouvements.

SoldeStock conserve ce total en cache pour éviter d'agréger tout l'historique à
chaque lecture, et porte les seuils de la section 7.2. Il est toujours
recalculable à partir du journal : c'est le journal qui fait foi.
"""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from catalogue.models import Produit
from core.models import Site


class TypeMouvement(models.TextChoices):
    ENTREE_ACHAT = "ENTREE_ACHAT", "Entrée — réception fournisseur"
    ENTREE_TRANSFERT = "ENTREE_TRANSFERT", "Entrée — transfert reçu"
    SORTIE_VENTE = "SORTIE_VENTE", "Sortie — vente"
    SORTIE_TRANSFERT = "SORTIE_TRANSFERT", "Sortie — transfert émis"
    PERTE = "PERTE", "Sortie — perte ou casse"
    AJUSTEMENT = "AJUSTEMENT", "Ajustement d'inventaire"
    ANNULATION = "ANNULATION", "Mouvement compensatoire d'annulation"
    # Approvisionnement école (M16)
    SORTIE_LIVRAISON_ECOLE = "SORTIE_LIVRAISON_ECOLE", "Sortie — livraison école (stock réservé)"
    ENTREE_LIVRAISON_ECOLE = "ENTREE_LIVRAISON_ECOLE", "Entrée — livraison reçue du magasin"
    RETOUR_LIVRAISON_ECOLE = "RETOUR_LIVRAISON_ECOLE", "Retour — réception partielle"
    # Approvisionnement magasin depuis dépôt (M17)
    SORTIE_APPRO_MAGASIN = "SORTIE_APPRO_MAGASIN", "Sortie — expédition vers magasin"
    ENTREE_APPRO_MAGASIN = "ENTREE_APPRO_MAGASIN", "Entrée — réception depuis dépôt"
    SORTIE_DON = "SORTIE_DON", "Sortie — don"
    SORTIE_SURPLUS = "SORTIE_SURPLUS", "Sortie — surplus retiré"


class SoldeStock(models.Model):
    """Solde courant et paramétrage d'une référence sur un site."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="soldes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="soldes")

    quantite = models.IntegerField(default=0, help_text="Somme des mouvements. Peut être négatif : c'est une alerte, pas un bug.")
    stock_minimum = models.PositiveIntegerField(default=0, help_text="Quantité minimale absolue à maintenir.")
    stock_securite = models.PositiveIntegerField(default=0, help_text="Seuil déclenchant le réapprovisionnement.")
    stock_maximum = models.PositiveIntegerField(default=0, help_text="Plafond au-delà duquel on ne commande plus.")

    class Meta:
        verbose_name = "solde de stock"
        ordering = ["site", "produit"]
        constraints = [
            models.UniqueConstraint(fields=["site", "produit"], name="un_solde_par_site_et_produit"),
        ]

    def __str__(self):
        return f"{self.produit.code} @ {self.site.nom} : {self.quantite}"

    @property
    def sous_seuil(self):
        return self.quantite <= self.stock_securite

    @property
    def en_rupture(self):
        return self.quantite <= 0

    @property
    def en_surstock(self):
        return self.stock_maximum > 0 and self.quantite > self.stock_maximum

    def recalculer(self):
        """Recalcule le solde depuis le journal. Le journal fait toujours foi."""
        total = MouvementStock.objects.filter(site=self.site, produit=self.produit).aggregate(
            t=models.Sum("quantite")
        )["t"] or 0
        SoldeStock.objects.filter(pk=self.pk).update(quantite=total)
        self.quantite = total
        return total


class MouvementStock(models.Model):
    """Journal en ajout seul. Quantité positive = entrée, négative = sortie."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="mouvements")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="mouvements")
    type = models.CharField(max_length=30, choices=TypeMouvement.choices)
    quantite = models.IntegerField(help_text="Signée : positive pour une entrée, négative pour une sortie.")

    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)
    auteur = models.ForeignKey(
        "core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements"
    )
    reference_document = models.CharField(
        max_length=100, blank=True, help_text="Numéro de vente, de transfert ou d'inventaire à l'origine du mouvement."
    )
    commentaire = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "mouvement de stock"
        ordering = ["-horodatage"]
        indexes = [models.Index(fields=["site", "produit", "horodatage"])]
        constraints = [
            models.CheckConstraint(condition=~models.Q(quantite=0), name="mouvement_non_nul"),
        ]

    def __str__(self):
        return f"{self.get_type_display()} {self.quantite:+d} {self.produit.code} @ {self.site.nom}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(
                "Un mouvement de stock est immuable. Enregistrez un mouvement compensatoire."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Un mouvement de stock ne se supprime pas. Enregistrez un mouvement compensatoire."
        )


class StatutAjustement(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    VALIDE = "VALIDE", "Validé"
    ANNULE = "ANNULE", "Annulé"


class Ajustement(models.Model):
    """Correction de stock après écart constaté (M12). Validé par superviseur ou DG."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="ajustements")
    statut = models.CharField(max_length=12, choices=StatutAjustement.choices, default=StatutAjustement.BROUILLON)
    motif = models.CharField(max_length=255, help_text="Raison de l'ajustement : perte, casse, correction d'écart...")
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="ajustements_crees")
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ajustements_valides",
    )

    class Meta:
        verbose_name = "ajustement de stock"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Ajustement #{self.pk} — {self.site.nom}"


class AjustementLigne(models.Model):
    ajustement = models.ForeignKey(Ajustement, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="ajustements")
    quantite = models.IntegerField(help_text="Signée : positive = entrée, négative = sortie/perte.")

    class Meta:
        verbose_name = "ligne d'ajustement"
        constraints = [
            models.UniqueConstraint(fields=["ajustement", "produit"], name="un_produit_par_ajustement"),
        ]

    def __str__(self):
        return f"{self.produit.code} : {self.quantite:+d}"
