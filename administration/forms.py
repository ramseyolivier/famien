import json

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from catalogue.models import CategorieProduit, Marque, Produit
from core.models import Commune, Profil, Site, TypeSite, Utilisateur
from kits.models import ClasseEcole, Kit, KitLigne


class CommuneForm(forms.ModelForm):
    class Meta:
        model = Commune
        fields = ["nom"]
        labels = {"nom": "Nom de la commune"}


class CategorieProduitForm(forms.ModelForm):
    class Meta:
        model = CategorieProduit
        fields = ["nom"]
        labels = {"nom": "Nom de la catégorie"}


class MagasinForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["nom", "commune", "adresse", "actif"]
        labels = {
            "nom": "Nom du magasin",
            "commune": "Commune",
            "adresse": "Adresse",
            "actif": "Actif",
        }

    def save(self, commit=True):
        site = super().save(commit=False)
        site.type = TypeSite.MAGASIN
        if commit:
            site.save()
        return site


class EcoleForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["nom", "commune", "adresse", "magasin_rattachement", "remise_convention", "actif"]
        labels = {
            "nom": "Nom de l'établissement",
            "commune": "Commune",
            "adresse": "Adresse",
            "magasin_rattachement": "Magasin de rattachement",
            "remise_convention": "Remise convention (%)",
            "actif": "Actif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["magasin_rattachement"].queryset = Site.objects.filter(
            type=TypeSite.MAGASIN, actif=True
        )

    def save(self, commit=True):
        site = super().save(commit=False)
        site.type = TypeSite.ECOLE
        if commit:
            site.save()
        return site


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ["code", "designation", "categorie", "marque", "unite", "cout_achat", "actif"]
        labels = {
            "code": "Code produit",
            "designation": "Désignation",
            "categorie": "Catégorie",
            "marque": "Marque",
            "unite": "Unité",
            "cout_achat": "Coût d'achat (F CFA)",
            "actif": "Actif",
        }


class MarqueForm(forms.ModelForm):
    class Meta:
        model = Marque
        fields = ["nom"]
        labels = {"nom": "Nom de la marque"}


class ClasseEcoleForm(forms.ModelForm):
    """Formulaire pour créer ou modifier une classe d'école."""

    class Meta:
        model = ClasseEcole
        fields = ["ecole", "niveau", "libelle"]
        labels = {
            "ecole": "École",
            "niveau": "Niveau scolaire",
            "libelle": "Intitulé de la classe",
        }
        help_texts = {
            "libelle": "Ex : 3ème A, 4ème Allemand, Terminale D…",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ecole"].queryset = Site.objects.filter(type=TypeSite.ECOLE, actif=True).order_by("nom")


class KitCreationForm(forms.ModelForm):
    """Formulaire pour créer un nouveau kit (école + classe + prix)."""

    class Meta:
        model = Kit
        fields = ["ecole", "classe", "prix_vente"]
        labels = {
            "ecole": "École",
            "classe": "Classe",
            "prix_vente": "Prix de vente du kit (F CFA)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ecole"].queryset = Site.objects.filter(type=TypeSite.ECOLE, actif=True).order_by("nom")
        self.fields["classe"].queryset = ClasseEcole.objects.select_related("ecole").order_by("ecole__nom", "niveau", "libelle")


class KitPrixForm(forms.Form):
    """Formulaire partiel pour modifier uniquement le prix d'un kit existant."""

    prix_vente = forms.DecimalField(
        label="Prix de vente du kit (F CFA)",
        min_value=0,
        decimal_places=2,
        max_digits=10,
    )


class KitLigneForm(forms.Form):
    produit = forms.ModelChoiceField(
        queryset=Produit.objects.filter(actif=True).order_by("code"),
        label="Produit",
        empty_label="— Choisir —",
    )
    quantite = forms.IntegerField(label="Qté", min_value=1, initial=1)


KitLigneFormSet = forms.formset_factory(KitLigneForm, extra=1, can_delete=True)


PREFIXE_PROFIL = {
    Profil.DG:           "DGE",
    Profil.MANAGER:      "MGR",
    Profil.SUPERVISEUR:  "SUP",
    Profil.GEST_MAGASIN: "GST",
    Profil.CHEF_EQUIPE:  "CHF",
    Profil.COMMERCIAL:   "COM",
}


def _appliquer_prefixe_prenom(prenom, profil):
    """Retire tout préfixe existant sur le prénom puis applique celui du profil."""
    prefixes = set(PREFIXE_PROFIL.values())
    base = prenom
    for p in prefixes:
        if prenom.upper().startswith(f"{p}-"):
            base = prenom[len(p) + 1:]
            break
    prefix = PREFIXE_PROFIL.get(profil, "")
    return f"{prefix}-{base}" if prefix else base


class UtilisateurCreationForm(forms.ModelForm):
    mot_de_passe = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput,
        help_text="8 caractères minimum.",
    )
    confirmation = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput,
    )

    class Meta:
        model = Utilisateur
        fields = ["username", "first_name", "last_name", "profil", "commune", "site", "is_active"]
        labels = {
            "username": "Identifiant",
            "first_name": "Prénom",
            "last_name": "Nom",
            "profil": "Profil / rôle",
            "commune": "Commune de supervision",
            "site": "Site de rattachement",
            "is_active": "Compte actif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["profil"].required = True
        self.fields["profil"].initial = ""
        self.fields["profil"].widget.choices = [("", "— Choisir un profil —")] + [
            (k, v) for k, v in self.fields["profil"].widget.choices if k != ""
        ]

    def clean(self):
        cleaned = super().clean()
        mdp = cleaned.get("mot_de_passe")
        conf = cleaned.get("confirmation")
        if mdp and conf and mdp != conf:
            raise ValidationError({"confirmation": "Les deux mots de passe ne correspondent pas."})
        if mdp:
            try:
                validate_password(mdp)
            except ValidationError as e:
                raise ValidationError({"mot_de_passe": e.messages})
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["mot_de_passe"])
        profil = self.cleaned_data.get("profil")
        if profil and user.first_name:
            user.first_name = _appliquer_prefixe_prenom(user.first_name, profil)
        if commit:
            user.save()
        return user


class UtilisateurModificationForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ["username", "first_name", "last_name", "profil", "commune", "site", "is_active"]
        labels = {
            "username": "Identifiant",
            "first_name": "Prénom",
            "last_name": "Nom",
            "profil": "Profil / rôle",
            "commune": "Commune de supervision",
            "site": "Site de rattachement",
            "is_active": "Compte actif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        profil = self.cleaned_data.get("profil")
        if profil and user.first_name:
            user.first_name = _appliquer_prefixe_prenom(user.first_name, profil)
        if commit:
            user.save()
        return user


class ReinitialisationMdpForm(forms.Form):
    nouveau_mot_de_passe = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput,
    )
    confirmation = forms.CharField(
        label="Confirmer",
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned = super().clean()
        mdp = cleaned.get("nouveau_mot_de_passe")
        conf = cleaned.get("confirmation")
        if mdp and conf and mdp != conf:
            raise ValidationError({"confirmation": "Les deux mots de passe ne correspondent pas."})
        if mdp:
            try:
                validate_password(mdp)
            except ValidationError as e:
                raise ValidationError({"nouveau_mot_de_passe": e.messages})
        return cleaned
