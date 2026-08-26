"""
Approvisionnement des écoles depuis les magasins (M16).

Flux : le chef d'équipe crée une commande (BROUILLON → SOUMISE), le gestionnaire
du magasin rattaché la traite (SOUMISE → LIVREE en débitant le stock magasin et
créant une réservation), puis le chef confirme la réception (LIVREE → RECUE en
créditant le stock école et libérant la réservation).

La réservation (StockReserve) permet de calculer le stock disponible réel au
magasin (solde − réservations) de manière à ne pas promettre le même article
à deux écoles différentes.

Section 16 du cahier des charges.
"""

from django.core.validators import MinValueValidator
from django.db import models, transaction


class StatutCommandeMagasin(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMISE = "SOUMISE", "Soumise"
    VALIDEE = "VALIDEE", "Validée"
    LIVREE = "LIVREE", "Livrée — en transit"
    RECUE = "RECUE", "Reçue"
    REJETEE = "REJETEE", "Rejetée"


class StatutCommandeEcole(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMISE = "SOUMISE", "Soumise"
    VALIDEE = "VALIDEE", "Validée"
    LIVREE = "LIVREE", "Livrée — en attente de réception"
    RECUE = "RECUE", "Reçue"
    REJETEE = "REJETEE", "Rejetée"
    ANNULEE = "ANNULEE", "Annulée"


class CommandeEcole(models.Model):
    """Demande d'approvisionnement émise par une école vers son magasin rattaché.

    Flux : BROUILLON → SOUMISE (chef) → VALIDEE (superviseur, crée StockReserve)
           → LIVREE (gestionnaire, ajuste StockReserve) → RECUE (chef, débit magasin + crédit école).
    Section 16 du cahier des charges.
    """

    ecole = models.ForeignKey(
        "core.Site",
        on_delete=models.PROTECT,
        related_name="commandes_ecole",
        limit_choices_to={"type": "ECOLE"},
    )
    statut = models.CharField(
        max_length=10,
        choices=StatutCommandeEcole.choices,
        default=StatutCommandeEcole.BROUILLON,
    )
    observations = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        related_name="commandes_ecole_creees",
    )
    soumise_le = models.DateTimeField(null=True, blank=True)
    soumise_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_ecole_soumises",
    )
    validee_le = models.DateTimeField(null=True, blank=True)
    validee_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_ecole_validees",
    )
    livree_le = models.DateTimeField(null=True, blank=True)
    livree_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_ecole_livrees",
    )
    livraison_close = models.BooleanField(default=False)
    recue_le = models.DateTimeField(null=True, blank=True)
    recue_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_ecole_recues",
    )
    motif_rejet = models.CharField(max_length=500, blank=True)
    rejete_le = models.DateTimeField(null=True, blank=True)
    rejete_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_ecole_rejetees",
    )

    numero_local = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "commande école"
        verbose_name_plural = "commandes école"
        ordering = ["-cree_le"]
        constraints = [
            models.UniqueConstraint(fields=["ecole", "numero_local"], name="numero_local_unique_ecole"),
        ]

    @property
    def numero(self):
        return self.numero_local or self.pk

    def save(self, *args, **kwargs):
        if self.pk is None and self.numero_local is None:
            with transaction.atomic():
                dernier = (
                    CommandeEcole.objects.select_for_update()
                    .filter(ecole=self.ecole)
                    .order_by("-numero_local")
                    .values_list("numero_local", flat=True)
                    .first()
                ) or 0
                self.numero_local = dernier + 1
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Commande #{self.numero} — {self.ecole.nom} ({self.get_statut_display()})"


class CommandeEcoleLigne(models.Model):
    """Ligne d'une commande école : un produit avec les quantités à chaque étape."""

    commande = models.ForeignKey(
        CommandeEcole,
        on_delete=models.CASCADE,
        related_name="lignes",
    )
    produit = models.ForeignKey(
        "catalogue.Produit",
        on_delete=models.PROTECT,
        related_name="lignes_commande_ecole",
    )
    quantite_demandee = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantite_livree = models.PositiveIntegerField(null=True, blank=True)
    quantite_deja_livree = models.PositiveIntegerField(null=True, blank=True, default=0)
    quantite_recue = models.PositiveIntegerField(null=True, blank=True)
    quantite_deja_recue = models.PositiveIntegerField(null=True, blank=True, default=0)
    motif_ecart = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "ligne de commande école"
        verbose_name_plural = "lignes de commande école"
        constraints = [
            models.UniqueConstraint(
                fields=["commande", "produit"],
                name="un_produit_par_commande_ecole",
            ),
        ]

    def __str__(self):
        return f"{self.produit.code} × {self.quantite_demandee}"


class StockReserve(models.Model):
    """
    Réservation de stock magasin pour une école.

    Créée lors de la validation de livraison par le gestionnaire, supprimée à
    la réception par le chef. Elle permet de soustraire du stock disponible les
    quantités déjà promises à d'autres écoles — évitant ainsi la survente.
    """

    magasin = models.ForeignKey(
        "core.Site",
        on_delete=models.PROTECT,
        related_name="stocks_reserves",
        limit_choices_to={"type": "MAGASIN"},
    )
    ecole = models.ForeignKey(
        "core.Site",
        on_delete=models.PROTECT,
        related_name="stocks_reserves_ecole",
        limit_choices_to={"type": "ECOLE"},
    )
    commande = models.ForeignKey(
        CommandeEcole,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    produit = models.ForeignKey(
        "catalogue.Produit",
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    quantite = models.PositiveIntegerField()

    class Meta:
        verbose_name = "stock réservé"
        verbose_name_plural = "stocks réservés"
        constraints = [
            models.UniqueConstraint(
                fields=["commande", "produit"],
                name="une_reservation_par_commande_produit",
            ),
        ]

    def __str__(self):
        return f"Réservation {self.produit.code} × {self.quantite} pour {self.ecole.nom}"


class CommandeMagasin(models.Model):
    """Demande d'approvisionnement d'un magasin depuis le dépôt général (M17)."""

    magasin = models.ForeignKey(
        "core.Site",
        on_delete=models.PROTECT,
        related_name="commandes_magasin",
        limit_choices_to={"type": "MAGASIN"},
    )
    statut = models.CharField(
        max_length=12,
        choices=StatutCommandeMagasin.choices,
        default=StatutCommandeMagasin.BROUILLON,
    )
    observations = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    cree_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        related_name="commandes_magasin_creees",
    )
    soumise_le = models.DateTimeField(null=True, blank=True)
    soumise_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_magasin_soumises",
    )
    validee_le = models.DateTimeField(null=True, blank=True)
    validee_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_magasin_validees",
    )
    livree_le = models.DateTimeField(null=True, blank=True)
    livree_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_magasin_livrees",
    )
    recue_le = models.DateTimeField(null=True, blank=True)
    recue_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_magasin_recues",
    )
    motif_rejet = models.CharField(max_length=500, blank=True)
    rejete_le = models.DateTimeField(null=True, blank=True)
    rejete_par = models.ForeignKey(
        "core.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commandes_magasin_rejetees",
    )
    livraison_close = models.BooleanField(default=False)
    numero_local = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "commande magasin"
        ordering = ["-cree_le"]
        constraints = [
            models.UniqueConstraint(fields=["magasin", "numero_local"], name="numero_local_unique_magasin"),
        ]

    @property
    def numero(self):
        return self.numero_local or self.pk

    def save(self, *args, **kwargs):
        if self.pk is None and self.numero_local is None:
            with transaction.atomic():
                dernier = (
                    CommandeMagasin.objects.select_for_update()
                    .filter(magasin=self.magasin)
                    .order_by("-numero_local")
                    .values_list("numero_local", flat=True)
                    .first()
                ) or 0
                self.numero_local = dernier + 1
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CM #{self.numero} — {self.magasin.nom} ({self.get_statut_display()})"


class CommandeMagasinLigne(models.Model):
    commande = models.ForeignKey(
        CommandeMagasin,
        on_delete=models.CASCADE,
        related_name="lignes",
    )
    produit = models.ForeignKey(
        "catalogue.Produit",
        on_delete=models.PROTECT,
        related_name="lignes_commande_magasin",
    )
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantite_deja_livree = models.PositiveIntegerField(default=0)          # cumul inter-tournées — déclaré par le dépôt
    quantite_deja_recue = models.PositiveIntegerField(default=0)           # cumul inter-tournées — confirmé par le magasin
    quantite_livree = models.PositiveIntegerField(null=True, blank=True)  # renseigné par DG/Manager (tournée en cours)
    quantite_recue = models.PositiveIntegerField(null=True, blank=True)   # renseigné par GEST_MAGASIN (tournée en cours)
    motif_ecart = models.CharField(max_length=300, blank=True)            # obligatoire si quantite_recue ≠ quantite_livree

    class Meta:
        verbose_name = "ligne de commande magasin"
        constraints = [
            models.UniqueConstraint(
                fields=["commande", "produit"],
                name="un_produit_par_commande_magasin",
            ),
        ]

    def __str__(self):
        return f"{self.produit.code} × {self.quantite}"


class StockReserveDepot(models.Model):
    """
    Réservation de stock dépôt pour une CommandeMagasin en cours de livraison.

    Flux commande normale : créée à la validation (SOUMISE → VALIDEE), ajustée
    aux quantités expédiées à la livraison (VALIDEE → LIVREE), supprimée à la
    réception (LIVREE → RECUE) après les mouvements de stock.

    Flux livraison directe [LD] : créée à la validation (BROUILLON → LIVREE),
    supprimée à la réception (LIVREE → RECUE) de la même façon.

    Permet d'afficher un stock disponible au dépôt qui exclut les quantités
    déjà engagées vers les magasins, quel que soit le circuit.

    Section M17 du cahier des charges.
    """

    commande = models.ForeignKey(
        CommandeMagasin,
        on_delete=models.CASCADE,
        related_name="reservations_depot",
    )
    produit = models.ForeignKey(
        "catalogue.Produit",
        on_delete=models.PROTECT,
        related_name="reservations_depot",
    )
    quantite = models.PositiveIntegerField()

    class Meta:
        verbose_name = "stock réservé dépôt"
        verbose_name_plural = "stocks réservés dépôt"
        constraints = [
            models.UniqueConstraint(
                fields=["commande", "produit"],
                name="une_reservation_depot_par_commande_produit",
            ),
        ]

    def __str__(self):
        return f"Réservation dépôt {self.produit.code} × {self.quantite} (CM #{self.commande_id})"
