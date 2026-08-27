"""
Entités structurantes du réseau FAMIEN : sites, utilisateurs.

Deux rôles uniquement : DG (accès national, peut vendre) et CHEF_EQUIPE
(rattaché à un site, peut vendre sur ce site). Pas d'intermédiaire.
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Profil(models.TextChoices):
    DG = "DG", "Directeur Général"
    CHEF_EQUIPE = "CHEF_EQUIPE", "Chef d'équipe"


class TypeSite(models.TextChoices):
    SITE = "SITE", "Site"


class Site(models.Model):
    """Point de vente du réseau FAMIEN. Chaque site porte son propre stock."""

    type = models.CharField(max_length=10, choices=TypeSite.choices, default=TypeSite.SITE)
    nom = models.CharField(max_length=150, unique=True)
    code = models.CharField(
        max_length=10, blank=True,
        help_text="Code court pour les numéros de documents (ex. SIT01).",
    )
    adresse = models.CharField(max_length=255, blank=True)
    actif = models.BooleanField(default=True)
    remise_convention = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Remise en %, accordée au personnel administratif.",
    )

    class Meta:
        verbose_name = "site"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    @property
    def est_ecole(self):
        """Compatibilité avec le code existant — tous les sites sont des points de vente."""
        return True


class SequenceCompteur(models.Model):
    """Compteur de séquence par clé (format : VTE-SIT01-2607). RG-M00 §3.2."""

    cle = models.CharField(max_length=50, primary_key=True)
    valeur = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "compteur de séquence"

    def __str__(self):
        return f"{self.cle} → {self.valeur}"


class Utilisateur(AbstractUser):
    """Utilisateur rattaché à un profil (DG ou CHEF_EQUIPE) et à un site."""

    profil = models.CharField(max_length=20, choices=Profil.choices, default=Profil.CHEF_EQUIPE)
    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="utilisateurs",
        help_text="Site de rattachement (obligatoire pour un chef d'équipe).",
    )
    derniere_activite = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "utilisateur"

    def __str__(self):
        nom = self.get_full_name() or self.username
        return f"{nom} ({self.get_profil_display()})"

    def clean(self):
        if self.profil == Profil.CHEF_EQUIPE and not self.site_id:
            raise ValidationError({"site": "Un chef d'équipe doit être rattaché à un site."})

    # --- Périmètre d'accès ---

    @property
    def acces_national(self):
        return self.is_superuser or self.profil == Profil.DG

    def sites_autorises(self):
        """QuerySet des sites que cet utilisateur a le droit de consulter."""
        if self.acces_national:
            return Site.objects.all()
        if self.site_id:
            return Site.objects.filter(pk=self.site_id)
        return Site.objects.none()

    def peut_acceder_au_site(self, site):
        """Cloisonnement effectif entre sites."""
        site_id = site.pk if isinstance(site, Site) else site
        return self.sites_autorises().filter(pk=site_id).exists()

    def peut_vendre(self):
        """DG et chef d'équipe peuvent vendre, à condition d'avoir un site."""
        return self.site_id is not None

    def peut_voir_ventes(self):
        """Les deux rôles voient les ventes de leur périmètre."""
        return True


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
