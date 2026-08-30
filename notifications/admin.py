from django.contrib import admin

from .models import EmailLog, Notification, PushSubscription, SMSLog, WhatsAppLog


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "type_evenement", "statut_envoi", "statut_livraison", "commande", "date_envoi")
    list_filter = ("type_evenement", "statut_envoi", "statut_livraison")
    search_fields = ("destinataire", "message", "reference_externe")
    readonly_fields = [f.name for f in SMSLog._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(WhatsAppLog)
class WhatsAppLogAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "commande", "statut_envoi", "date_envoi")
    list_filter = ("statut_envoi",)
    search_fields = ("destinataire",)
    readonly_fields = [f.name for f in WhatsAppLog._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "sujet", "type_evenement", "statut_envoi", "commande", "date_envoi")
    list_filter = ("type_evenement", "statut_envoi")
    search_fields = ("destinataire", "sujet")
    readonly_fields = [f.name for f in EmailLog._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("message", "role_cible", "type_evenement", "commande", "lu", "date_creation")
    list_filter = ("role_cible", "type_evenement", "lu")
    search_fields = ("message",)
    readonly_fields = ("role_cible", "type_evenement", "commande", "message", "date_creation")

    def has_add_permission(self, request):
        return False


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "endpoint", "date_creation")
    search_fields = ("user__username", "endpoint")
    readonly_fields = ("user", "endpoint", "p256dh", "auth", "date_creation")

    def has_add_permission(self, request):
        return False
