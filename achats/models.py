"""
Workflow d'achat : Commande fournisseur → Réception (M14-M15).
Les demandes d'achat ont été fusionnées dans le bon de commande (3 niveaux de validation).
Chaque étape est immuable une fois validée.
"""
from django.core.validators import MinValueValidator
from django.db import models


class StatutCommande(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumise"
    VALIDE_N1 = "VALIDE_N1", "Validée superviseur"
    VALIDE = "VALIDE", "Validée"
    CLOTURE = "CLOTURE", "Clôturée (entièrement reçue)"
    REJETE = "REJETE", "Rejetée"
    ANNULE = "ANNULE", "Annulée"


class CommandeFournisseur(models.Model):
    """Bon de commande fournisseur (M14). Workflow : BROUILLON → SOUMIS → VALIDE_N1 → VALIDE."""
    fournisseur = models.ForeignKey("catalogue.Fournisseur", on_delete=models.PROTECT, related_name="commandes")
    site_destination = models.ForeignKey("core.Site", on_delete=models.PROTECT, related_name="commandes_recues")
    statut = models.CharField(max_length=12, choices=StatutCommande.choices, default=StatutCommande.BROUILLON)
    observations = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="commandes_creees")
    soumis_le = models.DateTimeField(null=True, blank=True)
    soumis_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="commandes_soumises")
    valide_n1_le = models.DateTimeField(null=True, blank=True)
    valide_n1_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="commandes_validees_n1")
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="commandes_validees")
    modifie_le = models.DateTimeField(null=True, blank=True)
    modifie_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="commandes_modifiees")
    motif_rejet = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "commande fournisseur"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"CF #{self.pk} — {self.fournisseur} ({self.get_statut_display()})"


class CommandeFournisseurLigne(models.Model):
    commande = models.ForeignKey(CommandeFournisseur, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="lignes_commande")
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "ligne de commande"
        constraints = [
            models.UniqueConstraint(fields=["commande", "produit"], name="un_produit_par_commande"),
        ]

    def __str__(self):
        return f"{self.quantite} × {self.produit.code}"


class StatutReception(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    VALIDE = "VALIDE", "Validée"
    CLOTURE = "CLOTURE", "Clôturée"
    ANNULE = "ANNULE", "Annulée"


class Reception(models.Model):
    """Réception d'une commande fournisseur ou livraison directe (M15). Génère les entrées en stock."""
    commande = models.ForeignKey(
        CommandeFournisseur, on_delete=models.PROTECT, related_name="receptions",
        null=True, blank=True,
    )
    site_destination = models.ForeignKey(
        "core.Site", on_delete=models.PROTECT, related_name="receptions_directes",
        null=True, blank=True,
    )
    fournisseur = models.ForeignKey(
        "catalogue.Fournisseur", on_delete=models.PROTECT, related_name="receptions_directes",
        null=True, blank=True,
    )
    statut = models.CharField(max_length=12, choices=StatutReception.choices, default=StatutReception.BROUILLON)
    observations = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="receptions_creees")
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="receptions_validees")

    class Meta:
        verbose_name = "réception"
        ordering = ["-cree_le"]

    def __str__(self):
        if self.commande_id:
            return f"REC #{self.pk} — {self.commande.fournisseur}"
        fourn = self.fournisseur.raison_sociale if self.fournisseur_id else "Fournisseur inconnu"
        return f"REC #{self.pk} — Libre ({fourn})"

    @property
    def reference(self):
        if self.commande_id:
            n = Reception.objects.filter(commande_id=self.commande_id, pk__lte=self.pk).count()
            return f"{self.pk}RC#{n} — CF#{self.commande_id}"
        return f"{self.pk}RX"

    @property
    def titre(self):
        if self.commande_id:
            n = Reception.objects.filter(commande_id=self.commande_id, pk__lte=self.pk).count()
            return f"Réception #{n} de la commande #{self.commande_id}"
        return f"Réception directe #{self.pk}"

    @property
    def site_effectif(self):
        return self.commande.site_destination if self.commande_id else self.site_destination

    @property
    def fournisseur_effectif(self):
        return self.commande.fournisseur if self.commande_id else self.fournisseur


class ReceptionLigne(models.Model):
    reception = models.ForeignKey(Reception, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("catalogue.Produit", on_delete=models.PROTECT, related_name="lignes_reception")
    quantite_attendue = models.PositiveIntegerField(default=0)
    quantite_recue = models.PositiveIntegerField(default=0)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conforme = models.BooleanField(default=True)
    justification_ecart = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "ligne de réception"
        constraints = [
            models.UniqueConstraint(fields=["reception", "produit"], name="un_produit_par_reception"),
        ]

    def __str__(self):
        return f"{self.produit.code} : {self.quantite_recue}/{self.quantite_attendue}"

    @property
    def ecart(self):
        return self.quantite_recue - self.quantite_attendue

    @property
    def montant(self):
        return self.prix_unitaire * self.quantite_recue
