"""
Transferts de stock entre sites (M11 — section 7.5 du CDC).
Cycle : émetteur envoie → stock débité immédiatement (EN_ATTENTE) →
destinataire accepte (stock crédité) ou rejette (stock recrédité à l'émetteur).
"""
from django.core.validators import MinValueValidator
from django.db import models


class StatutTransfert(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    ACCEPTE = "ACCEPTE", "Accepté"
    REJETE = "REJETE", "Rejeté"


class Transfert(models.Model):
    site_origine = models.ForeignKey("core.Site", on_delete=models.PROTECT, related_name="transferts_emis")
    site_destination = models.ForeignKey("core.Site", on_delete=models.PROTECT, related_name="transferts_recus")
    statut = models.CharField(max_length=12, choices=StatutTransfert.choices, default=StatutTransfert.EN_ATTENTE)
    observations = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="transferts_crees")
    traite_le = models.DateTimeField(null=True, blank=True)
    traite_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transferts_traites",
    )

    class Meta:
        verbose_name = "transfert"
        ordering = ["-cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(site_origine=models.F("site_destination")),
                name="transfert_origine_destination_differents",
            )
        ]

    def __str__(self):
        return f"Transfert #{self.pk} : {self.site_origine.nom} → {self.site_destination.nom}"


class TransfertLigne(models.Model):
    transfert = models.ForeignKey(Transfert, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="lignes_transfert")
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "ligne de transfert"
        constraints = [
            models.UniqueConstraint(fields=["transfert", "produit"], name="un_produit_par_transfert"),
        ]

    def __str__(self):
        return f"{self.quantite} × {self.produit.code}"
