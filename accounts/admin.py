from django.contrib import admin, messages
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Le rôle par défaut est « Formation sanitaire » : un compte créé ici sans
        # fiche ne peut pas se connecter, et rien ne le signalait.
        if obj.est_fosa_sans_fiche:
            messages.warning(
                request,
                f"Le compte « {obj.username} » a le rôle Formation sanitaire mais aucune fiche "
                "ne lui est rattachée : il ne pourra pas se connecter. Rattachez-le à une fiche "
                "dans « Formations sanitaires », ou changez son rôle s'il s'agit du personnel "
                "FRPS. Pour une FOSA du Nord déjà importée, activez plutôt son compte existant.",
            )


@admin.register(FormationSanitaire)
class FormationSanitaireAdmin(admin.ModelAdmin):
    list_display = ("nom", "region", "district", "telephone_contact", "actif", "date_creation")
    list_filter = ("region", "actif")
    search_fields = ("nom", "region", "district")
    autocomplete_fields = ("user",)
