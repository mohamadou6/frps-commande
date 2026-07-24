from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import FormationSanitaire, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Utilisé par un admin FRPS pour créer les comptes (formations sanitaires et personnel).

    Il n'y a pas d'auto-inscription : seul un admin peut créer des utilisateurs ici.
    """

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Rôle FRPS", {"fields": ("role", "telephone")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Rôle FRPS", {"fields": ("role", "telephone")}),
    )
    list_display = ("username", "get_full_name", "role", "telephone", "is_active")
    list_filter = BaseUserAdmin.list_filter + ("role",)


@admin.register(FormationSanitaire)
class FormationSanitaireAdmin(admin.ModelAdmin):
    list_display = ("nom", "region", "district", "telephone_contact", "actif", "date_creation")
    list_filter = ("region", "actif")
    search_fields = ("nom", "region", "district")
    autocomplete_fields = ("user",)
