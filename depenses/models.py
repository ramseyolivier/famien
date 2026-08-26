"""Dépenses opérationnelles (M20) et versements hiérarchiques."""
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class CategorieDepense(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "catégorie de dépense"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class StatutDepense(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    VALIDE = "VALIDE", "Validé"
    CONFIRME = "CONFIRME", "Confirmé"
    REJETE = "REJETE", "Rejeté"


class Depense(models.Model):
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT, null=True, blank=True, related_name="depenses")
    categorie = models.ForeignKey(CategorieDepense, on_delete=models.PROTECT, related_name="depenses")
    montant = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    motif = models.CharField(max_length=500)
    statut = models.CharField(max_length=12, choices=StatutDepense.choices, default=StatutDepense.BROUILLON)
    date_depense = models.DateField(help_text="Date effective de la dépense.")
    piece_justificative = models.CharField(max_length=500, blank=True, help_text="Référence ou description du justificatif.")
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="depenses_creees")
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="depenses_validees")
    montant_confirme = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    confirme_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="depenses_confirmees")
    confirme_le = models.DateTimeField(null=True, blank=True)
    motif_rejet = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "dépense"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["site", "date_depense"])]

    def __str__(self):
        site_str = self.site.nom if self.site_id else "Superviseur"
        return f"Dépense #{self.pk} — {self.montant:,.0f} F CFA — {site_str}"


class ModeVersement(models.TextChoices):
    ESPECES        = "ESPECES",        "Espèces"
    MOBILE_MONEY   = "MOBILE_MONEY",   "Mobile money"
    VIREMENT_BANQUE = "VIREMENT_BANQUE", "Virement bancaire"


class StatutVersement(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    CONFIRME   = "CONFIRME",   "Confirmé"
    REJETE     = "REJETE",     "Rejeté"


class Versement(models.Model):
    """Remontée d'argent dans la hiérarchie : chef → superviseur → DG/Manager."""
    verseur      = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="versements_effectues")
    destinataire = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="versements_recus")
    montant      = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(1)])
    date         = models.DateField()
    mode         = models.CharField(max_length=15, choices=ModeVersement.choices)
    reference    = models.CharField(max_length=200, blank=True, help_text="Numéro de transaction mobile money ou référence.")
    note         = models.TextField(blank=True)
    statut       = models.CharField(max_length=12, choices=StatutVersement.choices, default=StatutVersement.EN_ATTENTE)
    cree_le      = models.DateTimeField(auto_now_add=True, db_index=True)
    traite_le    = models.DateTimeField(null=True, blank=True)
    motif_rejet  = models.CharField(max_length=500, blank=True)
    recu_banque  = models.ImageField(upload_to="versements/recus/", null=True, blank=True)

    class Meta:
        verbose_name = "versement"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Versement {self.montant:,.0f} F — {self.verseur} → {self.destinataire}"
