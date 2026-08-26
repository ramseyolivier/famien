from django.contrib import admin
from .models import ActionCorrective, NonConformite


class ActionInline(admin.TabularInline):
    model = ActionCorrective
    extra = 0
    readonly_fields = ["cree_par", "cree_le"]


@admin.register(NonConformite)
class NonConformiteAdmin(admin.ModelAdmin):
    list_display = ["titre", "site", "type", "statut", "cree_par", "cree_le"]
    list_filter = ["statut", "type", "site"]
    search_fields = ["titre", "description"]
    inlines = [ActionInline]
    readonly_fields = ["cree_par", "cree_le", "cloture_le", "cloture_par"]
