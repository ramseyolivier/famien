from django.contrib import admin
from .models import CategorieDepense, Depense

@admin.register(CategorieDepense)
class CategorieDepenseAdmin(admin.ModelAdmin):
    list_display = ["nom"]
    search_fields = ["nom"]

@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ["pk", "site", "categorie", "montant", "date_depense", "statut"]
    list_filter = ["statut", "site", "categorie"]
    search_fields = ["motif"]
