"""
Inventaires physiques (M10 — section 7.2 du CDC).
La validation génère un mouvement AJUSTEMENT pour chaque écart constaté.
"""
from django.db import models
from django.db.models import F


class StatutInventaire(models.TextChoices):
    EN_COURS = "EN_COURS", "En cours de saisie"
    VALIDE = "VALIDE", "Validé"
    ANNULE = "ANNULE", "Annulé"


class Inventaire(models.Model):
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT, related_name="inventaires")
    statut = models.CharField(max_length=12, choices=StatutInventaire.choices, default=StatutInventaire.EN_COURS)
    observations = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="inventaires_crees")
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventaires_valides",
    )

    class Meta:
        verbose_name = "inventaire"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Inventaire #{self.pk} — {self.site.nom}"

    @property
    def nb_ecarts(self):
        return self.lignes.exclude(quantite_physique=F("quantite_theorique")).count()


class InventaireLigne(models.Model):
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="lignes_inventaire")
    quantite_theorique = models.IntegerField(default=0, help_text="Solde calculé au moment de la saisie.")
    quantite_physique = models.IntegerField(default=0, help_text="Quantité comptée physiquement.")
    commentaire = models.CharField(max_length=300, blank=True, default="", help_text="Explication de l'écart constaté.")

    class Meta:
        verbose_name = "ligne d'inventaire"
        ordering = ["produit__code"]
        constraints = [
            models.UniqueConstraint(fields=["inventaire", "produit"], name="un_produit_par_inventaire"),
        ]

    def __str__(self):
        return f"{self.produit.code} : théo={self.quantite_theorique} / physique={self.quantite_physique}"

    @property
    def ecart(self):
        return self.quantite_physique - self.quantite_theorique
