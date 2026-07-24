import logging
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger("notifications.whatsapp")


class WhatsAppBackend(ABC):
    @abstractmethod
    def send_document(
        self, numero: str, pdf_bytes: bytes, filename: str, caption: str, media_url: str | None = None
    ) -> bool:
        """Envoie un document (PDF) par WhatsApp. Retourne True si réussi.

        `media_url` est un lien public HTTPS vers le PDF (nécessaire pour les
        fournisseurs, comme Twilio, qui téléchargent le fichier eux-mêmes
        plutôt que de recevoir les octets directement).
        """
        raise NotImplementedError


class LogWhatsAppBackend(WhatsAppBackend):
    """Backend par défaut tant qu'aucune API WhatsApp réelle n'est branchée."""

    def send_document(
        self, numero: str, pdf_bytes: bytes, filename: str, caption: str, media_url: str | None = None
    ) -> bool:
        logger.info("[WhatsApp mock] à %s : %s (%s, %d octets, url=%s)", numero, caption, filename, len(pdf_bytes), media_url)
        return True


class TwilioWhatsAppBackend(WhatsAppBackend):
    """Envoi réel via l'API WhatsApp de Twilio.

    Nécessite dans le .env : TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM (numéro sandbox ou numéro WhatsApp Twilio approuvé)
    et PUBLIC_BASE_URL (URL publique HTTPS du serveur Django, ex: tunnel
    ngrok en dev) : Twilio télécharge le PDF via `media_url`, il doit donc
    être accessible publiquement (pas localhost).

    Important : en mode sandbox, chaque numéro destinataire doit d'abord
    envoyer le message "join <code-sandbox>" au numéro Twilio WhatsApp
    depuis WhatsApp, sinon Twilio refuse l'envoi vers ce numéro.
    """

    def send_document(
        self, numero: str, pdf_bytes: bytes, filename: str, caption: str, media_url: str | None = None
    ) -> bool:
        from twilio.rest import Client

        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        whatsapp_from = settings.TWILIO_WHATSAPP_FROM
        if not account_sid or not auth_token or not whatsapp_from:
            raise RuntimeError(
                "TwilioWhatsAppBackend nécessite TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN et "
                "TWILIO_WHATSAPP_FROM dans le .env"
            )
        if not media_url:
            raise RuntimeError(
                "TwilioWhatsAppBackend nécessite une media_url publique (vérifier PUBLIC_BASE_URL dans le .env)"
            )

        client = Client(account_sid, auth_token)
        destinataire = numero if numero.startswith("whatsapp:") else f"whatsapp:{numero}"
        expediteur = whatsapp_from if whatsapp_from.startswith("whatsapp:") else f"whatsapp:{whatsapp_from}"

        message = client.messages.create(
            from_=expediteur,
            to=destinataire,
            body=caption,
            media_url=[media_url],
        )
        return bool(message.sid)


class RealWhatsAppBackend(WhatsAppBackend):
    """Squelette pour l'API WhatsApp Business (Meta Cloud API).

    À compléter une fois l'accès disponible : settings.WHATSAPP_API_URL,
    settings.WHATSAPP_API_TOKEN. Contrairement à Twilio, l'API Meta permet
    d'uploader directement les octets du PDF (pas besoin de media_url
    publique) - à adapter selon la doc Meta (upload média puis envoi par
    media id).
    """

    def send_document(
        self, numero: str, pdf_bytes: bytes, filename: str, caption: str, media_url: str | None = None
    ) -> bool:
        import requests

        api_url = settings.WHATSAPP_API_URL
        api_token = settings.WHATSAPP_API_TOKEN
        if not api_url or not api_token:
            raise RuntimeError(
                "RealWhatsAppBackend nécessite WHATSAPP_API_URL et WHATSAPP_API_TOKEN dans le .env"
            )

        # TODO: adapter au format exact de l'API WhatsApp retenue (upload média + envoi message document).
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_token}"},
            data={"to": numero, "caption": caption},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            timeout=20,
        )
        response.raise_for_status()
        return True


def get_whatsapp_backend() -> WhatsAppBackend:
    backend_name = getattr(settings, "WHATSAPP_BACKEND", "log")
    if backend_name == "twilio":
        return TwilioWhatsAppBackend()
    if backend_name == "real":
        return RealWhatsAppBackend()
    return LogWhatsAppBackend()
