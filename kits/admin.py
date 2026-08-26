from django.contrib import admin

from .models import ClasseEcole, Kit, KitLigne


@admin.register(ClasseEcole)
class ClasseEcoleAdmin(admin.ModelAdmin):
    list_display = ["ecole", "niveau", "libelle"]
    list_filter = ["niveau", "ecole"]
    search_fields = ["libelle", "ecole__nom"]
    autocomplete_fields = ["ecole"]


class KitLigneInline(admin.TabularInline):
    model = KitLigne
    extra = 3
    autocomplete_fields = ["produit"]


@admin.register(Kit)
class KitAdmin(admin.ModelAdmin):
    list_display = [
        "ecole", "classe", "version", "actif", "nombre_articles",
        "cout_revient_affiche", "prix_vente", "total_detail_affiche", "marge_affichee",
    ]
    list_filter = ["actif", "classe__niveau", "ecole"]
    search_fields = ["ecole__nom", "classe__libelle"]
    autocomplete_fields = ["ecole", "classe"]
    inlines = [KitLigneInline]
    readonly_fields = ["version", "cree_le", "cree_par"]

    @admin.display(description="coût de revient")
    def cout_revient_affiche(self, obj):
        return f"{obj.cout_revient:,.0f} F"

    @admin.display(description="somme prix détail")
    def total_detail_affiche(self, obj):
        return f"{obj.total_prix_detail:,.0f} F"

    @admin.display(description="marge")
    def marge_affichee(self, obj):
        return f"{obj.marge:,.0f} F"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # La règle « prix du kit < somme des prix de détail » ne peut être vérifiée
        # qu'une fois les lignes enregistrées.
        form.instance.verifier_regle_de_prix()
