from django.contrib import admin

from .models import Fournisseur, Marque, Produit, ProduitFournisseur


class OffreInline(admin.TabularInline):
    model = ProduitFournisseur
    extra = 0
    autocomplete_fields = ["fournisseur"]


@admin.register(Marque)
class MarqueAdmin(admin.ModelAdmin):
    search_fields = ["nom"]


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ["code", "designation", "categorie", "marque", "cout_achat", "prix_detail", "actif"]
    list_filter = ["categorie", "marque", "actif"]
    search_fields = ["code", "designation"]
    list_editable = ["cout_achat", "prix_detail"]
    inlines = [OffreInline]


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ["raison_sociale", "contact", "telephone", "actif"]
    search_fields = ["raison_sociale", "contact"]
