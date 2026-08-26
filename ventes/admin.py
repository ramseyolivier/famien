from django.contrib import admin

from .models import LigneProduitVente, LigneVente, Vente


class LigneVenteInline(admin.TabularInline):
    model = LigneVente
    extra = 0
    can_delete = False
    readonly_fields = ["kit", "produit", "quantite", "prix_unitaire"]


class LigneProduitVenteInline(admin.TabularInline):
    model = LigneProduitVente
    extra = 0
    can_delete = False
    readonly_fields = ["produit", "quantite_due", "quantite_servie", "quantite_manquante"]

    @admin.display(description="manquant")
    def quantite_manquante(self, obj):
        return obj.quantite_manquante


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ["numero", "horodatage", "ecole", "vendeuse", "montant_total", "mode_paiement", "statut"]
    list_filter = ["statut", "mode_paiement", "ecole", "horodatage"]
    search_fields = ["numero", "vendeuse__username"]
    date_hierarchy = "horodatage"
    inlines = [LigneVenteInline, LigneProduitVenteInline]
    readonly_fields = [f.name for f in Vente._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
