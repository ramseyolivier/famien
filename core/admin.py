from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Commune, Site, Utilisateur


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ["nom", "nombre_de_sites"]
    search_fields = ["nom"]

    @admin.display(description="sites")
    def nombre_de_sites(self, obj):
        return obj.sites.count()


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["nom", "type", "commune", "magasin_rattachement", "remise_convention", "actif"]
    list_filter = ["type", "commune", "actif"]
    search_fields = ["nom", "adresse"]
    autocomplete_fields = ["magasin_rattachement"]

    class Media:
        js = ("js/admin_site.js",)


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ["username", "get_full_name", "profil", "commune", "site", "is_active"]
    list_filter = ["profil", "commune", "is_active"]
    autocomplete_fields = ["site"]
    fieldsets = UserAdmin.fieldsets + (
        ("Périmètre LEPAD", {"fields": ("profil", "commune", "site")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Périmètre LEPAD", {"fields": ("profil", "commune", "site")}),
    )
