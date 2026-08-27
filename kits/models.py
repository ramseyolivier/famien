"""
Kits scolaires (section 7.7) : composition par établissement et par classe.

Le versionnage est natif : modifier un kit publié ne l'écrase pas, il crée une
version suivante et archive la précédente. Une vente conserve donc pour
toujours la composition exacte au moment où elle a été faite — indispensable
quand un parent revient trois semaines plus tard contester le contenu.

Chaque kit est rattaché à une ClasseEcole (ex : "3ème A", "4ème Allemand") plutôt
qu'à un niveau générique, pour permettre des compositions différentes au sein du
même niveau selon les professeurs ou les options.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

from catalogue.models import Produit
from core.models import Site


class Niveau(models.TextChoices):
    SIXIEME = "6E", "6ème"
    CINQUIEME = "5E", "5ème"
    QUATRIEME = "4E", "4ème"
    TROISIEME = "3E", "3ème"
    SECONDE_A = "2NDA", "2nde A"
    SECONDE_C = "2NDC", "2nde C"
    PREMIERE_A = "1REA", "1ère A"
    PREMIERE_C = "1REC", "1ère C"
    PREMIERE_D = "1RED", "1ère D"
    TERMINALE_A = "TLEA", "Terminale A"
    TERMINALE_C = "TLEC", "Terminale C"
    TERMINALE_D = "TLED", "Terminale D"


class ClasseEcole(models.Model):
    """
    Classe d'une école (ex : "3ème A", "4ème Allemand").
    Le niveau sert uniquement au groupement et aux filtres ; le libellé est libre.
    """
    ecole = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name="classes"
    )
    niveau = models.CharField(max_length=6, choices=Niveau.choices)
    libelle = models.CharField(
        max_length=100,
        help_text="Intitulé exact de la classe (ex : 3ème A, 4ème Allemand, 3ème B…)"
    )

    class Meta:
        verbose_name = "classe"
        verbose_name_plural = "classes"
        ordering = ["ecole__nom", "niveau", "libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["ecole", "libelle"],
                name="une_classe_par_ecole_et_libelle"
            )
        ]

    def __str__(self):
        return f"{self.libelle} — {self.ecole.nom}"


class Kit(models.Model):
    ecole = models.ForeignKey(
        Site, on_delete=models.PROTECT, related_name="kits"
    )
    classe = models.ForeignKey(
        ClasseEcole, on_delete=models.PROTECT, related_name="kits"
    )
    version = models.PositiveIntegerField(default=1)
    actif = models.BooleanField(default=True, help_text="Une seule version active par classe.")

    prix_vente = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)],
        help_text="Prix réduit du kit, en F CFA.",
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(
        "core.Utilisateur", on_delete=models.PROTECT, null=True, blank=True, related_name="kits_crees"
    )

    class Meta:
        verbose_name = "kit scolaire"
        ordering = ["ecole__nom", "classe__libelle", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["classe", "version"], name="une_version_par_classe"
            ),
            models.UniqueConstraint(
                fields=["classe"],
                condition=models.Q(actif=True),
                name="un_seul_kit_actif_par_classe",
            ),
        ]

    def __str__(self):
        return f"Kit {self.classe.libelle} — {self.ecole.nom} (v{self.version})"

    @property
    def cout_revient(self):
        """Somme des coûts d'achat unitaires multipliés par les quantités."""
        return sum(
            (ligne.produit.cout_achat * ligne.quantite for ligne in self.lignes.all()),
            Decimal("0"),
        )

    @property
    def total_prix_detail(self):
        """Ce que coûterait le même contenu acheté article par article."""
        return sum(
            (ligne.produit.prix_detail * ligne.quantite for ligne in self.lignes.all()),
            Decimal("0"),
        )

    @property
    def economie_client(self):
        return self.total_prix_detail - self.prix_vente

    @property
    def marge(self):
        return self.prix_vente - self.cout_revient

    @property
    def nombre_articles(self):
        return sum(ligne.quantite for ligne in self.lignes.all())

    def clean(self):
        if self.classe_id and self.ecole_id and self.classe.ecole_id != self.ecole_id:
            raise ValidationError({"classe": "La classe sélectionnée n'appartient pas à ce site."})

    def verifier_regle_de_prix(self):
        """
        Le prix de vente du kit doit couvrir au minimum la somme des coûts d'achat
        des articles qui le composent — on ne vend pas à perte.
        """
        cout = self.cout_revient
        if cout and self.prix_vente <= cout:
            raise ValidationError(
                f"Le prix du kit ({self.prix_vente:,.0f} F CFA) doit être supérieur à la somme "
                f"des coûts d'achat ({cout:,.0f} F CFA)."
            )

    @transaction.atomic
    def nouvelle_version(self, auteur=None):
        """Archive la version courante et renvoie une copie modifiable."""
        lignes = list(self.lignes.all())
        Kit.objects.filter(pk=self.pk).update(actif=False)
        suivant = Kit.objects.create(
            ecole=self.ecole,
            classe=self.classe,
            version=self.version + 1,
            actif=True,
            prix_vente=self.prix_vente,
            cree_par=auteur,
        )
        KitLigne.objects.bulk_create(
            [KitLigne(kit=suivant, produit=l.produit, quantite=l.quantite) for l in lignes]
        )
        return suivant


class KitLigne(models.Model):
    kit = models.ForeignKey(Kit, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="lignes_kit")
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "ligne de kit"
        ordering = ["produit__code"]
        constraints = [
            models.UniqueConstraint(fields=["kit", "produit"], name="un_produit_une_fois_par_kit"),
        ]

    def __str__(self):
        return f"{self.quantite} × {self.produit.code}"
