"""Référentiel produit et fournisseurs (annexe A et section 7.4 du cahier des charges)."""

from django.core.validators import MinValueValidator
from django.db import models


class CategorieProduit(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "catégorie"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Marque(models.Model):
    nom = models.CharField(max_length=80, unique=True)

    class Meta:
        verbose_name = "marque"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Produit(models.Model):
    """Une référence du catalogue. `code` sert aux tables de formation de kits."""

    code = models.CharField(max_length=20, unique=True, help_text="Ex. C200, ET300GF, TP100.")
    designation = models.CharField(max_length=200)
    categorie = models.ForeignKey(
        CategorieProduit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="produits",
    )
    marque = models.ForeignKey(Marque, on_delete=models.PROTECT, null=True, blank=True, related_name="produits")
    unite = models.CharField(max_length=20, default="unité")

    cout_achat = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text="Coût d'achat unitaire de référence, en F CFA. Base du coût de revient des kits.",
    )
    prix_detail = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text="Prix de vente à l'unité, en F CFA. Non affiché publiquement (section 7.7).",
    )
    actif = models.BooleanField(default=True)

    def prix_pour_ecole(self, ecole):
        override = self.prix_ecoles.filter(ecole=ecole).first()
        return override.prix_detail if override else self.prix_detail

    class Meta:
        verbose_name = "produit"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.designation}"


class Fournisseur(models.Model):
    raison_sociale = models.CharField(max_length=200, unique=True)
    contact = models.CharField(max_length=200, blank=True)
    telephone = models.CharField(max_length=40, blank=True)
    conditions_paiement = models.CharField(max_length=200, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "fournisseur"
        ordering = ["raison_sociale"]

    def __str__(self):
        return self.raison_sociale


class ProduitFournisseur(models.Model):
    """Prix d'achat d'une référence chez un fournisseur donné (comparatif, section 7.3)."""

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="offres")
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.CASCADE, related_name="offres")
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    delai_livraison_jours = models.PositiveIntegerField(default=7)

    class Meta:
        verbose_name = "offre fournisseur"
        constraints = [
            models.UniqueConstraint(fields=["produit", "fournisseur"], name="offre_unique_par_couple"),
        ]

    def __str__(self):
        return f"{self.produit.code} chez {self.fournisseur}"


class PrixEcole(models.Model):
    """Prix de vente au détail d'un produit pour une école donnée.
    Si absent, le prix global Produit.prix_detail s'applique (§7.7 du SRS)."""

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name="prix_ecoles")
    ecole = models.ForeignKey(
        "core.Site", on_delete=models.CASCADE, related_name="prix_produits"
    )
    prix_detail = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = "prix école"
        constraints = [
            models.UniqueConstraint(
                fields=["produit", "ecole"], name="prix_unique_par_produit_et_ecole"
            ),
        ]

    def __str__(self):
        return f"{self.produit.code} @ {self.ecole} : {self.prix_detail} F"
