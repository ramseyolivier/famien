from django.contrib import admin
from django.utils.html import format_html

from .models import MouvementStock, SoldeStock


@admin.register(SoldeStock)
class SoldeStockAdmin(admin.ModelAdmin):
    list_display = ["produit", "site", "quantite", "stock_securite", "stock_maximum", "etat"]
    list_filter = ["site__type", "site", "produit__categorie"]
    search_fields = ["produit__code", "produit__designation", "site__nom"]
    list_editable = ["stock_securite", "stock_maximum"]
    autocomplete_fields = ["site", "produit"]
    readonly_fields = ["quantite"]

    @admin.display(description="état")
    def etat(self, obj):
        if obj.en_rupture:
            return format_html('<b style="color:#C0342A">Rupture</b>')
        if obj.sous_seuil:
            return format_html('<b style="color:#B8860B">Sous seuil</b>')
        return "OK"


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    """Journal en lecture seule : un mouvement ne se modifie ni ne se supprime."""

    list_display = ["horodatage", "site", "produit", "type", "quantite", "reference_document", "auteur"]
    list_filter = ["type", "site", "horodatage"]
    search_fields = ["produit__code", "reference_document", "commentaire"]
    date_hierarchy = "horodatage"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
