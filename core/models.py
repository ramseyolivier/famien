"""
Entités structurantes du réseau LEPAD : zones, sites, utilisateurs.

Choix de modélisation important — le MCD du cahier des charges (section 14)
sépare MAGASIN et ÉCOLE en deux entités, mais fait porter à MOUVEMENT_STOCK,
TRANSFERT et INVENTAIRE un champ « site_id (magasin ou école) » ambigu.
On unifie donc les deux dans une seule table Site avec un discriminant `type`.
Toutes les clés étrangères de stock deviennent des FK simples, contraintes
par la base, au lieu de relations génériques invérifiables.
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Profil(models.TextChoices):
    DG = "DG", "Directeur Général"
    MANAGER = "MANAGER", "Manager Général"
    SUPERVISEUR = "SUPERVISEUR", "Superviseur de zone"
    GEST_MAGASIN = "GEST_MAGASIN", "Gestionnaire de magasin"
    CHEF_EQUIPE = "CHEF_EQUIPE", "Chef d'équipe"
    COMMERCIAL = "COMMERCIAL", "Commercial / Caissière"


class TypeSite(models.TextChoices):
    DEPOT = "DEPOT", "Dépôt général"
    MAGASIN = "MAGASIN", "Magasin"
    ECOLE = "ECOLE", "École"


class Commune(models.Model):
    """Subdivision administrative (arrondissement d'Abidjan) où se trouvent les sites."""

    nom = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "commune"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Site(models.Model):
    """Un magasin ou un établissement scolaire. Chaque site porte son propre stock."""

    type = models.CharField(max_length=10, choices=TypeSite.choices)
    nom = models.CharField(max_length=150)
    commune = models.ForeignKey(
        Commune,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sites",
    )
    code = models.CharField(
        max_length=10, blank=True,
        help_text="Code court pour les numéros de documents (ex. MFB pour Mamie Fétaï Bingerville).",
    )
    adresse = models.CharField(max_length=255, blank=True)
    actif = models.BooleanField(default=True)

    magasin_rattachement = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ecoles_approvisionnees",
        limit_choices_to={"type": TypeSite.MAGASIN},
        help_text="Magasin qui approvisionne cette école.",
    )
    remise_convention = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Remise en %, accordée au personnel administratif de l'établissement.",
    )

    class Meta:
        verbose_name = "site"
        ordering = ["type", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["type", "nom"], name="site_nom_unique_par_type"),
            models.CheckConstraint(
                condition=models.Q(type="ECOLE") | models.Q(magasin_rattachement__isnull=True),
                name="seule_une_ecole_a_un_magasin_de_rattachement",
            ),
        ]

    def __str__(self):
        return self.nom

    def clean(self):
        if self.type == TypeSite.DEPOT:
            if self.commune_id:
                raise ValidationError({"commune": "Le dépôt général n'est pas rattaché à une commune."})
            if self.magasin_rattachement_id:
                raise ValidationError({"magasin_rattachement": "Le dépôt général ne peut pas avoir de magasin de rattachement."})
        elif self.type == TypeSite.ECOLE:
            if self.magasin_rattachement is None:
                raise ValidationError({"magasin_rattachement": "Une école doit être rattachée à un magasin."})
        if self.magasin_rattachement_id and self.magasin_rattachement_id == self.pk:
            raise ValidationError({"magasin_rattachement": "Un site ne peut pas se rattacher à lui-même."})

    @property
    def est_ecole(self):
        return self.type == TypeSite.ECOLE


class SequenceCompteur(models.Model):
    """Compteur de séquence par clé (format : VTE-MFB-2607). RG-M00 §3.2."""

    cle = models.CharField(max_length=50, primary_key=True)
    valeur = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "compteur de séquence"

    def __str__(self):
        return f"{self.cle} → {self.valeur}"


class Utilisateur(AbstractUser):
    """Utilisateur rattaché à un profil et à un périmètre (zone ou site)."""

    profil = models.CharField(max_length=20, choices=Profil.choices, default=Profil.COMMERCIAL)
    commune = models.ForeignKey(
        Commune,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="utilisateurs",
        help_text="Commune de supervision (superviseur de zone).",
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="utilisateurs",
        help_text="Site de rattachement : école pour un commercial, magasin pour un gestionnaire.",
    )
    derniere_activite = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "utilisateur"

    def __str__(self):
        nom = self.get_full_name() or self.username
        return f"{nom} ({self.get_profil_display()})"

    def clean(self):
        # Superviseur : commune obligatoire, jamais de site
        if self.profil == Profil.SUPERVISEUR:
            if self.site_id:
                raise ValidationError({"site": "Un superviseur est rattaché à une commune, pas à un site."})
        # Gestionnaire : site obligatoire de type Magasin
        elif self.profil == Profil.GEST_MAGASIN:
            if self.site_id and self.site.type != TypeSite.MAGASIN:
                raise ValidationError({"site": "Un gestionnaire doit être rattaché à un magasin, pas à une école."})
        # Chef d'équipe / Caissière : site obligatoire de type École
        elif self.profil in {Profil.CHEF_EQUIPE, Profil.COMMERCIAL}:
            if self.site_id and self.site.type != TypeSite.ECOLE:
                raise ValidationError({"site": "Un chef d'équipe ou une caissière doit être rattaché à une école."})
        # DG / Manager : aucun site (ou dépôt général uniquement)
        elif self.profil in {Profil.DG, Profil.MANAGER}:
            if self.site_id and self.site.type != TypeSite.DEPOT:
                raise ValidationError({"site": "Un DG ou Manager ne peut être rattaché qu'au dépôt général (ou aucun site)."})

    # --- Périmètre d'accès : matrice de droits, section 15 du cahier des charges ---

    @property
    def acces_national(self):
        return self.is_superuser or self.profil in {Profil.DG, Profil.MANAGER}

    def sites_autorises(self):
        """QuerySet des sites que cet utilisateur a le droit de consulter."""
        if self.acces_national:
            return Site.objects.all()
        if self.profil == Profil.SUPERVISEUR and self.commune_id:
            return Site.objects.filter(commune_id=self.commune_id)
        if self.site_id:
            return Site.objects.filter(pk=self.site_id)
        return Site.objects.none()

    def peut_acceder_au_site(self, site):
        """Cloisonnement effectif entre écoles et entre zones — critère de recette n°5."""
        site_id = site.pk if isinstance(site, Site) else site
        return self.sites_autorises().filter(pk=site_id).exists()

    def peut_vendre(self):
        return self.profil == Profil.COMMERCIAL and self.site_id is not None

    def peut_voir_ventes(self):
        """Le gestionnaire de magasin ne consulte que le stock, pas les ventes."""
        return self.profil != Profil.GEST_MAGASIN


class TypeNotification(models.TextChoices):
    RUPTURE_STOCK = "RUPTURE_STOCK", "Rupture de stock"
    DEMANDE_SOUMISE = "DEMANDE_SOUMISE", "Demande d'achat soumise"
    DEMANDE_VALIDEE = "DEMANDE_VALIDEE", "Demande d'achat validée"
    DEMANDE_REJETEE = "DEMANDE_REJETEE", "Demande d'achat rejetée"
    DEPENSE_SOUMISE = "DEPENSE_SOUMISE", "Dépense soumise"
    DEPENSE_VALIDEE = "DEPENSE_VALIDEE", "Dépense validée"
    DEPENSE_REJETEE = "DEPENSE_REJETEE", "Dépense rejetée"
    TRANSFERT_RECU = "TRANSFERT_RECU", "Transfert reçu"
    TRANSFERT_ACCEPTE = "TRANSFERT_ACCEPTE", "Transfert accepté"
    TRANSFERT_REJETE = "TRANSFERT_REJETE", "Transfert rejeté"
    TRANSFERT_VALIDE = "TRANSFERT_VALIDE", "Transfert validé"
    INVENTAIRE_VALIDE = "INVENTAIRE_VALIDE", "Inventaire validé"
    VENTE_ANNULEE = "VENTE_ANNULEE", "Vente annulée"
    DEMANDE_ANNULATION = "DEMANDE_ANNULATION", "Demande d'annulation de vente"
    ANNULATION_REJETEE = "ANNULATION_REJETEE", "Demande d'annulation rejetée"
    LIVRAISON_PRETE = "LIVRAISON_PRETE", "Livraison prête à réceptionner"
    LIVRAISON_CONFIRMEE = "LIVRAISON_CONFIRMEE", "Livraison confirmée"
    LIVRAISON_REFUSEE = "LIVRAISON_REFUSEE", "Livraison refusée"
    VERSEMENT_RECU = "VERSEMENT_RECU", "Versement reçu à approuver"
    VERSEMENT_CONFIRME = "VERSEMENT_CONFIRME", "Versement confirmé"
    VERSEMENT_REJETE = "VERSEMENT_REJETE", "Versement rejeté"
    INFO = "INFO", "Information"
    NON_CONFORMITE = "NON_CONFORMITE", "Non-conformité signalée"


TYPES_NOTIFICATION_STOCK = frozenset([
    TypeNotification.RUPTURE_STOCK,
    TypeNotification.DEMANDE_SOUMISE,
    TypeNotification.DEMANDE_VALIDEE,
    TypeNotification.DEMANDE_REJETEE,
    TypeNotification.DEPENSE_SOUMISE,
    TypeNotification.DEPENSE_VALIDEE,
    TypeNotification.DEPENSE_REJETEE,
    TypeNotification.TRANSFERT_RECU,
    TypeNotification.TRANSFERT_ACCEPTE,
    TypeNotification.TRANSFERT_REJETE,
    TypeNotification.TRANSFERT_VALIDE,
    TypeNotification.INVENTAIRE_VALIDE,
    TypeNotification.LIVRAISON_PRETE,
    TypeNotification.LIVRAISON_CONFIRMEE,
    TypeNotification.LIVRAISON_REFUSEE,
])


class Notification(models.Model):
    """Message de l'application vers un utilisateur. Jamais modifié, seulement marqué lu."""

    destinataire = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=20, choices=TypeNotification.choices)
    titre = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    lien = models.CharField(max_length=200, blank=True)
    lue = models.BooleanField(default=False)
    groupe = models.CharField(max_length=36, blank=True, default="", db_index=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "notification"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["destinataire", "lue", "-cree_le"])]

    def __str__(self):
        return f"[{self.type}] {self.titre} → {self.destinataire}"
