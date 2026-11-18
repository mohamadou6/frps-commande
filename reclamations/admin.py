from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import MessageReclamation, PhotoReclamation, Reclamation


class MessageReclamationInline(admin.TabularInline):
    model = MessageReclamation
    extra = 0
    readonly_fields = ("date", "auteur", "de_la_fosa", "texte")
    can_delete = False


class PhotoReclamationInline(admin.TabularInline):
    model = PhotoReclamation
    extra = 0
    fields = ("apercu", "message", "largeur", "hauteur", "date")
    readonly_fields = fields
    can_delete = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Photo")
    def apercu(self, photo):
        url = reverse("reclamations:photo", args=[photo.pk])
        return format_html('<a href="{}" target="_blank"><img src="{}" style="max-height:80px"></a>', url, url)


@admin.register(Reclamation)
class ReclamationAdmin(admin.ModelAdmin):
    list_display = ("id", "formation_sanitaire", "motif", "commande", "statut", "date_creation", "date_activite")
    list_filter = ("statut", "motif")
    search_fields = ("formation_sanitaire__nom", "description")
    readonly_fields = ("date_creation", "date_activite", "date_resolution")
    raw_id_fields = ("commande",)
    inlines = [MessageReclamationInline, PhotoReclamationInline]
