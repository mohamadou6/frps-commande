import logging
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger("notifications.sms")


class SMSBackend(ABC):
    """Interface d'envoi de SMS. Une seule méthode à implémenter par backend."""

    @abstractmethod
    def send(self, numero: str, message: str) -> str:
        """Envoie un SMS. Retourne une référence externe (resource_id Orange, SID
        Twilio...) utilisée pour corréler un futur accusé de livraison (DR) — chaîne
        vide si la passerelle n'en fournit pas. Lève une exception si l'envoi échoue."""
        raise NotImplementedError


class LogSMSBackend(SMSBackend):
    """Backend par défaut tant qu'aucune passerelle SMS réelle n'est branchée.

    N'envoie rien réellement : journalise le message (utile en dev/démo). Le
    SMSLog en base garde la trace de tous les envois quel que soit le backend.
    """

    def send(self, numero: str, message: str) -> str:
        logger.info("[SMS mock] à %s : %s", numero, message)
        return ""


class TwilioSMSBackend(SMSBackend):
    """Envoi réel de SMS via Twilio.

    Nécessite dans le .env : TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN (déjà
    utilisés pour WhatsApp) et TWILIO_SMS_FROM (numéro Twilio acheté, avec
    capacité SMS).
    """

    def send(self, numero: str, message: str) -> str:
        from twilio.rest import Client

        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        sms_from = settings.TWILIO_SMS_FROM
        if not account_sid or not auth_token or not sms_from:
            raise RuntimeError(
                "TwilioSMSBackend nécessite TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN et TWILIO_SMS_FROM dans le .env"
            )

        client = Client(account_sid, auth_token)

        # Un SID renvoyé ici prouve seulement que Twilio a ACCEPTÉ le message, pas
        # qu'il a été livré : un SMS peut rester au statut « sent » indéfiniment si
        # l'opérateur destinataire ne le remet jamais (constaté vers le Cameroun en
        # août 2026). On demande donc l'accusé de livraison, qui vient renseigner
        # SMSLog.statut_livraison via views.twilio_status_callback.
        parametres = {"from_": sms_from, "to": numero, "body": message}
        base_publique = (settings.PUBLIC_BASE_URL or "").rstrip("/")
        if base_publique.startswith("https://"):
            # Twilio exige une URL publique en HTTPS : en local (http://localhost)
            # on s'en passe plutôt que de faire échouer tout envoi.
            parametres["status_callback"] = f"{base_publique}/notifications/twilio-dlr/"

        sms = client.messages.create(**parametres)
        if not sms.sid:
            raise RuntimeError("Twilio n'a renvoyé aucun SID pour ce SMS")
        return sms.sid


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

    def send(self, numero: str, message: str) -> str:
        from urllib.parse import quote

        import requests

        sender_address = settings.ORANGE_SMS_SENDER_ADDRESS
        if not sender_address:
            raise RuntimeError("OrangeSMSBackend nécessite ORANGE_SMS_SENDER_ADDRESS dans le .env")

        jeton = self._obtenir_jeton()
        adresse_dest = numero if numero.startswith("tel:") else f"tel:{numero}"
        # Le segment tel:+237... doit être URL-encodé dans le chemin (doc Orange :
        # /outbound/tel%3A%2B{numero}/requests), sinon l'API renvoie une erreur.
        chemin_sender = quote(sender_address, safe="")

        requete = {
            "address": adresse_dest,
            "senderAddress": sender_address,
            "outboundSMSTextMessage": {"message": message},
        }
        if settings.ORANGE_SMS_SENDER_NAME:
            requete["senderName"] = settings.ORANGE_SMS_SENDER_NAME

        reponse = requests.post(
            f"https://api.orange.com/smsmessaging/v1/outbound/{chemin_sender}/requests",
            json={"outboundSMSMessageRequest": requete},
            headers={"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"},
            timeout=15,
        )
        try:
            reponse.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Orange SMS API a échoué ({reponse.status_code}) : {reponse.text}") from exc

        # Un 201 confirme seulement qu'Orange a accepté la requête, PAS que le SMS a
        # été livré (voir gotcha CLAUDE.md/mémoire) : le resourceURL renvoyé ici sert
        # à corréler le vrai statut de livraison reçu plus tard via le callback DR
        # (voir views.orange_dr_callback). On extrait le dernier segment de l'URL.
        try:
            resource_url = reponse.json()["outboundSMSMessageRequest"]["resourceURL"]
            return resource_url.rstrip("/").rsplit("/", 1)[-1]
        except (ValueError, KeyError, IndexError):
            logger.warning("Orange SMS: reponse 201 sans resourceURL exploitable: %s", reponse.text)
            return ""


class MTNSMSBackend(SMSBackend):
    """Envoi réel de SMS via l'API MTN Developer (produit "SMS V2"), pour une
    meilleure délivrabilité vers les numéros MTN Cameroun (Orange documente
    lui-même des soucis de livraison vers MTN, voir OrangeSMSBackend).

    Nécessite dans le .env : MTN_SMS_CLIENT_ID, MTN_SMS_CLIENT_SECRET (portail
    developers.mtn.com, app créée sur le produit "SMS V2") et
    MTN_SMS_SENDER_ADDRESS (MSISDN expéditeur approuvé par MTN, format
    ex: "+237XXXXXXXXX").

    Référence API (developers.mtn.com/products/mtn-sms-interface) :
    - Jeton : POST https://api.mtn.com/v1/oauth/access_token?grant_type=client_credentials
      (client_id/client_secret en corps x-www-form-urlencoded)
    - Envoi : POST https://api.mtn.com/v2/messages/sms/outbound
      {"senderAddress": ..., "receiverAddress": [...], "message": ...}
    - Statut de livraison (polling, pas de callback à héberger comme Orange) :
      GET https://api.mtn.com/v2/messages/sms/outbound/{senderAddress}/{transactionId}/deliveryStatus
      (voir verifier_statut_livraison_mtn ci-dessous)
    """

    def _obtenir_jeton(self) -> str:
        import requests

        client_id = settings.MTN_SMS_CLIENT_ID
        client_secret = settings.MTN_SMS_CLIENT_SECRET
        if not client_id or not client_secret:
            raise RuntimeError("MTNSMSBackend nécessite MTN_SMS_CLIENT_ID et MTN_SMS_CLIENT_SECRET dans le .env")

        reponse = requests.post(
            "https://api.mtn.com/v1/oauth/access_token",
            params={"grant_type": "client_credentials"},
            data={"client_id": client_id, "client_secret": client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        reponse.raise_for_status()
        return reponse.json()["access_token"]

    def send(self, numero: str, message: str) -> str:
        import requests

        sender_address = settings.MTN_SMS_SENDER_ADDRESS
        if not sender_address:
            raise RuntimeError("MTNSMSBackend nécessite MTN_SMS_SENDER_ADDRESS dans le .env")

        jeton = self._obtenir_jeton()
        requete = {
            "senderAddress": sender_address,
            "receiverAddress": [numero],
            # Max 160 caractères par la doc MTN (segment unique, même contrainte
            # que la limite deja appliquee cote _construire_message).
            "message": message[:160],
        }
        reponse = requests.post(
            "https://api.mtn.com/v2/messages/sms/outbound",
            json=requete,
            headers={"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"},
            timeout=15,
        )
        try:
            reponse.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"MTN SMS API a échoué ({reponse.status_code}) : {reponse.text}") from exc

        # Comme pour Orange, un succès HTTP ne garantit pas la livraison réelle.
        # transactionId sert à interroger le vrai statut (voir verifier_statut_livraison_mtn).
        try:
            return reponse.json()["transactionId"]
        except (ValueError, KeyError):
            logger.warning("MTN SMS: reponse succes sans transactionId exploitable: %s", reponse.text)
            return ""


def verifier_statut_livraison_mtn(transaction_id: str) -> dict:
    """Interroge l'API MTN (GET deliveryStatus) pour connaître le vrai statut de
    livraison d'un SMS envoyé via MTNSMSBackend — contrairement à Orange, pas besoin
    d'héberger un callback public : un simple GET suffit, testable en local."""
    import requests

    sender_address = settings.MTN_SMS_SENDER_ADDRESS
    backend = MTNSMSBackend()
    jeton = backend._obtenir_jeton()

    reponse = requests.get(
        f"https://api.mtn.com/v2/messages/sms/outbound/{sender_address}/{transaction_id}/deliveryStatus",
        headers={"Authorization": f"Bearer {jeton}"},
        timeout=15,
    )
    reponse.raise_for_status()
    return reponse.json()


class RealSMSBackend(SMSBackend):
    """Squelette générique pour une autre passerelle SMS réelle.

    À compléter avec l'URL de l'API et la clé fournies par le fournisseur SMS,
    puis basculer `SMS_BACKEND=real` dans le `.env`.
    """

    def send(self, numero: str, message: str) -> str:
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
        return ""


def get_sms_backend() -> SMSBackend:
    backend_name = getattr(settings, "SMS_BACKEND", "log")
    if backend_name == "twilio":
        return TwilioSMSBackend()
    if backend_name == "orange":
        return OrangeSMSBackend()
    if backend_name == "mtn":
        return MTNSMSBackend()
    if backend_name == "real":
        return RealSMSBackend()
    return LogSMSBackend()
