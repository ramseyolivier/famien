from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Site, Utilisateur


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["nom", "code", "remise_convention", "actif"]
    list_filter = ["actif"]
    search_fields = ["nom", "adresse"]


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ["username", "get_full_name", "profil", "site", "is_active"]
    list_filter = ["profil", "is_active"]
    autocomplete_fields = ["site"]
    fieldsets = UserAdmin.fieldsets + (
        ("Périmètre FAMIEN", {"fields": ("profil", "site")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Périmètre FAMIEN", {"fields": ("profil", "site")}),
    )
