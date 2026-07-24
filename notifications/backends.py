import logging
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger("notifications.sms")


class SMSBackend(ABC):
    """Interface d'envoi de SMS. Une seule méthode à implémenter par backend."""

    @abstractmethod
    def send(self, numero: str, message: str) -> bool:
        """Envoie un SMS. Retourne True si l'envoi a réussi, lève une exception sinon."""
        raise NotImplementedError


class LogSMSBackend(SMSBackend):
    """Backend par défaut tant qu'aucune passerelle SMS réelle n'est branchée.

    N'envoie rien réellement : journalise le message (utile en dev/démo). Le
    SMSLog en base garde la trace de tous les envois quel que soit le backend.
    """

    def send(self, numero: str, message: str) -> bool:
        logger.info("[SMS mock] à %s : %s", numero, message)
        return True


class TwilioSMSBackend(SMSBackend):
    """Envoi réel de SMS via Twilio.

    Nécessite dans le .env : TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN (déjà
    utilisés pour WhatsApp) et TWILIO_SMS_FROM (numéro Twilio acheté, avec
    capacité SMS).
    """

    def send(self, numero: str, message: str) -> bool:
        from twilio.rest import Client

        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        sms_from = settings.TWILIO_SMS_FROM
        if not account_sid or not auth_token or not sms_from:
            raise RuntimeError(
                "TwilioSMSBackend nécessite TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN et TWILIO_SMS_FROM dans le .env"
            )

        client = Client(account_sid, auth_token)
        sms = client.messages.create(from_=sms_from, to=numero, body=message)
        return bool(sms.sid)


class OrangeSMSBackend(SMSBackend):
    """Envoi réel de SMS via l'API Orange Developer (SMS API), pour une bien
    meilleure délivrabilité vers les numéros Orange Cameroun qu'un agrégateur
    international générique.

    Nécessite dans le .env : ORANGE_SMS_CLIENT_ID, ORANGE_SMS_CLIENT_SECRET
    (portail developer.orange.com, application "SMS API") et
    ORANGE_SMS_SENDER_ADDRESS (numéro/short code expéditeur approuvé par
    Orange, format ex: "tel:+237XXXXXXXXX").
    """

    def _obtenir_jeton(self) -> str:
        import base64

        import requests

        client_id = settings.ORANGE_SMS_CLIENT_ID
        client_secret = settings.ORANGE_SMS_CLIENT_SECRET
        if not client_id or not client_secret:
            raise RuntimeError(
                "OrangeSMSBackend nécessite ORANGE_SMS_CLIENT_ID et ORANGE_SMS_CLIENT_SECRET dans le .env"
            )

        identifiants = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        reponse = requests.post(
            "https://api.orange.com/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {identifiants}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=10,
        )
        reponse.raise_for_status()
        return reponse.json()["access_token"]

    def send(self, numero: str, message: str) -> bool:
        import requests

        sender_address = settings.ORANGE_SMS_SENDER_ADDRESS
        if not sender_address:
            raise RuntimeError("OrangeSMSBackend nécessite ORANGE_SMS_SENDER_ADDRESS dans le .env")

        jeton = self._obtenir_jeton()
        adresse_dest = numero if numero.startswith("tel:") else f"tel:{numero}"

        reponse = requests.post(
            f"https://api.orange.com/smsmessaging/v1/outbound/{sender_address}/requests",
            json={
                "outboundSMSMessageRequest": {
                    "address": [adresse_dest],
                    "senderAddress": sender_address,
                    "outboundSMSTextMessage": {"message": message},
                }
            },
            headers={"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"},
            timeout=15,
        )
        reponse.raise_for_status()
        return True


class RealSMSBackend(SMSBackend):
    """Squelette générique pour une autre passerelle SMS réelle.

    À compléter avec l'URL de l'API et la clé fournies par le fournisseur SMS,
    puis basculer `SMS_BACKEND=real` dans le `.env`.
    """

    def send(self, numero: str, message: str) -> bool:
        import requests

        api_url = settings.SMS_API_URL
        api_key = settings.SMS_API_KEY
        if not api_url or not api_key:
            raise RuntimeError(
                "RealSMSBackend nécessite SMS_API_URL et SMS_API_KEY dans le .env"
            )

        # TODO: adapter le payload/headers au format exact de la passerelle SMS retenue.
        response = requests.post(
            api_url,
            json={"to": numero, "message": message},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        return True


def get_sms_backend() -> SMSBackend:
    backend_name = getattr(settings, "SMS_BACKEND", "log")
    if backend_name == "twilio":
        return TwilioSMSBackend()
    if backend_name == "orange":
        return OrangeSMSBackend()
    if backend_name == "real":
        return RealSMSBackend()
    return LogSMSBackend()
