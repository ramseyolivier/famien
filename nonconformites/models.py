"""
Non-conformités détectées lors des réceptions, inventaires ou en cours d'activité.
Section M21 du cahier des charges.
"""

from django.db import models

from core.models import Site, Utilisateur


class TypeNonConformite(models.TextChoices):
    PRODUIT = "PRODUIT", "Défaut produit"
    PROCESSUS = "PROCESSUS", "Non-conformité processus"
    FRAUDE = "FRAUDE", "Fraude"
    AUTRE = "AUTRE", "Autre"


class StatutNonConformite(models.TextChoices):
    OUVERTE = "OUVERTE", "Ouverte"
    EN_COURS = "EN_COURS", "En cours de traitement"
    CLOTUREE = "CLOTUREE", "Clôturée"
    ANNULEE = "ANNULEE", "Annulée"


class NonConformite(models.Model):
    site = models.ForeignKey(
        Site, on_delete=models.PROTECT, null=True, blank=True, related_name="non_conformites"
    )
    type = models.CharField(max_length=20, choices=TypeNonConformite.choices)
    titre = models.CharField(max_length=200)
    description = models.TextField()
    statut = models.CharField(
        max_length=10, choices=StatutNonConformite.choices, default=StatutNonConformite.OUVERTE
    )
    cree_par = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="non_conformites_creees"
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    cloture_le = models.DateTimeField(null=True, blank=True)
    cloture_par = models.ForeignKey(
        Utilisateur,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="non_conformites_cloturees",
    )
    reference_document = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to="nonconformites/", null=True, blank=True)

    class Meta:
        verbose_name = "non-conformité"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"[{self.get_type_display()}] {self.titre}"

    @property
    def est_ouverte(self):
        return self.statut in {StatutNonConformite.OUVERTE, StatutNonConformite.EN_COURS}


class ActionCorrective(models.Model):
    """Action prise pour traiter une non-conformité."""

    non_conformite = models.ForeignKey(
        NonConformite, on_delete=models.CASCADE, related_name="actions"
    )
    description = models.TextField()
    cree_par = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="actions_correctives"
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "action corrective"
        ordering = ["cree_le"]

    def __str__(self):
        return f"Action sur NC #{self.non_conformite_id}"
