"""
Ventes (section 7.8) et file de livraison.

Deux détails de conception qui comptent :

1. `uuid` est généré par le navigateur, pas par le serveur. Sur un réseau
   instable, une requête qui expire côté client a pu aboutir côté serveur ; la
   vendeuse voit une erreur et retape la vente. La contrainte d'unicité sur
   l'uuid rend le réenregistrement inoffensif.

2. Le reçu papier sert aujourd'hui de jeton entre la caissière et le commercial
   qui constitue le kit. On le remplace par une file de livraison consultable en
   temps réel : la vente reste EN_ATTENTE jusqu'à remise physique du kit.
"""

import uuid as uuid_lib
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from catalogue.models import Produit
from core.models import Site
from kits.models import Kit


class ModePaiement(models.TextChoices):
    ESPECES = "ESPECES", "Espèces"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile money"
    AUTRE = "AUTRE", "Autre"


class StatutVente(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "Payée, à remettre"
    LIVREE = "LIVREE", "Livrée"
    PARTIELLE = "PARTIELLE", "Livrée partiellement"
    ANNULEE = "ANNULEE", "Annulée"


class Vente(models.Model):
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    numero = models.CharField(max_length=30, editable=False, help_text="Séquentiel par site.")

    ecole = models.ForeignKey(
        Site, on_delete=models.PROTECT, related_name="ventes"
    )
    vendeuse = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="ventes")
    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)

    telephone_client = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Numéro de téléphone du client — obligatoire quand la vente génère un avoir.",
    )

    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    montant_recu = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    remise = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Remise conventionnelle accordée au personnel administratif.",
    )
    mode_paiement = models.CharField(max_length=20, choices=ModePaiement.choices, default=ModePaiement.ESPECES)
    statut = models.CharField(max_length=12, choices=StatutVente.choices, default=StatutVente.EN_ATTENTE)
    observations = models.TextField(blank=True)

    livree_le = models.DateTimeField(null=True, blank=True)
    livree_par = models.ForeignKey(
        "core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="livraisons"
    )

    annulee_par = models.ForeignKey(
        "core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True,
        related_name="annulations_effectuees",
    )
    annulee_le = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True)

    annulation_demandee = models.BooleanField(default=False)
    motif_demande = models.TextField(blank=True)

    class Meta:
        verbose_name = "vente"
        ordering = ["-horodatage"]
        constraints = [
            models.UniqueConstraint(fields=["ecole", "numero"], name="numero_unique_par_ecole"),
        ]
        indexes = [models.Index(fields=["ecole", "statut"])]

    def __str__(self):
        return f"{self.numero} — {self.montant_total:,.0f} F CFA"

    @property
    def monnaie_rendue(self):
        if self.montant_recu:
            return max(Decimal("0"), self.montant_recu - self.montant_total)
        return None

    @property
    def reste_a_livrer(self):
        """Lignes produit non entièrement servies : le « solde à livrer » de la section 7.8."""
        return [l for l in self.lignes_produit.all() if l.quantite_manquante > 0]

    @property
    def est_complete(self):
        return not self.reste_a_livrer

    @property
    def modes_paiement_display(self):
        """Retourne les modes de paiement distincts des lignes, lisibles."""
        labels = {c: l for c, l in ModePaiement.choices}
        modes = list(dict.fromkeys(
            l.mode_paiement for l in self.lignes.all()
        ))
        return " + ".join(labels.get(m, m) for m in modes) if modes else self.get_mode_paiement_display()

    @property
    def delai_livraison_secondes(self):
        """Temps d'attente réel du client au stand. Indicateur absent du papier."""
        if not self.livree_le:
            return None
        return int((self.livree_le - self.horodatage).total_seconds())


class LigneVente(models.Model):
    """Ce que le client a acheté et payé : un kit, ou une référence au détail."""

    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name="lignes")
    kit = models.ForeignKey(Kit, on_delete=models.PROTECT, null=True, blank=True, related_name="lignes_vente")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, null=True, blank=True, related_name="lignes_vente")

    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(
        max_length=20, choices=ModePaiement.choices, default=ModePaiement.ESPECES,
        help_text="Mode de paiement choisi pour cette ligne spécifiquement.",
    )

    class Meta:
        verbose_name = "ligne de vente"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kit__isnull=False, produit__isnull=True)
                    | models.Q(kit__isnull=True, produit__isnull=False)
                ),
                name="ligne_vente_kit_ou_produit_exclusif",
            ),
        ]

    def __str__(self):
        cible = self.kit or self.produit
        return f"{self.quantite} × {cible}"

    @property
    def montant(self):
        return self.prix_unitaire * self.quantite

    @property
    def libelle(self):
        if self.kit_id:
            return f"Kit {self.kit.classe.libelle}"
        return self.produit.designation


class ClotureCaisse(models.Model):
    """Clôture journalière de caisse par école (M19)."""

    ecole = models.ForeignKey(
        Site, on_delete=models.PROTECT, related_name="clotures"
    )
    date = models.DateField(db_index=True)
    montant_especes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_mobile = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_autre = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nb_ventes = models.PositiveIntegerField(default=0)
    observations = models.TextField(blank=True)
    cloture_le = models.DateTimeField(auto_now_add=True)
    cloture_par = models.ForeignKey("core.Utilisateur", on_delete=models.PROTECT, related_name="clotures")

    class Meta:
        verbose_name = "clôture de caisse"
        ordering = ["-date", "ecole"]
        constraints = [
            models.UniqueConstraint(fields=["ecole", "date"], name="une_cloture_par_ecole_et_jour"),
        ]

    def __str__(self):
        return f"Clôture {self.ecole.nom} — {self.date}"

    @property
    def montant_total(self):
        return self.montant_especes + self.montant_mobile + self.montant_autre


class LigneProduitVente(models.Model):
    """
    Besoin en références, kits éclatés. C'est le niveau auquel on suit le stock
    et le reste à livrer, puisqu'une rupture porte sur un cahier précis et non
    sur le kit entier.
    """

    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name="lignes_produit")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="lignes_produit_vente")
    quantite_due = models.PositiveIntegerField()
    quantite_servie = models.PositiveIntegerField(default=0, help_text="Quantité effectivement sortie du stock.")
    prix_unitaire_avoir = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Prix unitaire du produit au moment de la vente, pour valoriser l'avoir.",
    )
    avoir_annule = models.BooleanField(default=False, help_text="L'avoir restant a été annulé — le client est remboursé.")
    avoir_annule_par = models.ForeignKey(
        "core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True,
        related_name="avoirs_annules",
    )
    avoir_annule_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "besoin produit d'une vente"
        ordering = ["produit__code"]
        constraints = [
            models.UniqueConstraint(fields=["vente", "produit"], name="un_besoin_par_vente_et_produit"),
        ]

    def __str__(self):
        return f"{self.produit.code} : {self.quantite_servie}/{self.quantite_due}"

    @property
    def quantite_manquante(self):
        if self.avoir_annule:
            return 0
        return max(self.quantite_due - self.quantite_servie, 0)

    @property
    def montant_avoir(self):
        return self.prix_unitaire_avoir * self.quantite_manquante
