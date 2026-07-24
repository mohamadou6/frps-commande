import logging
import uuid
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger("paiements.orange_money")


class PaymentGateway(ABC):
    @abstractmethod
    def initiate_payment(self, paiement) -> str:
        """Démarre le paiement, retourne une référence de transaction."""
        raise NotImplementedError

    @abstractmethod
    def handle_callback(self, payload: dict) -> tuple[str, bool]:
        """Traite le callback du fournisseur. Retourne (reference_transaction, succes)."""
        raise NotImplementedError


class MockOrangeMoneyGateway(PaymentGateway):
    """Simule Orange Money : confirme immédiatement le paiement.

    Permet de tester tout le parcours (commande -> paiement -> SMS reçu) sans
    accès réel à l'API Orange Money Cameroun.
    """

    def initiate_payment(self, paiement) -> str:
        reference = f"MOCK-{uuid.uuid4().hex[:10].upper()}"
        logger.info("[Orange Money mock] paiement initié pour commande #%s -> %s", paiement.commande_id, reference)
        return reference

    def handle_callback(self, payload: dict) -> tuple[str, bool]:
        return payload.get("reference_transaction", ""), True


class OrangeMoneyGateway(PaymentGateway):
    """Squelette d'intégration API Orange Money Cameroun (Web Payment).

    À compléter une fois les identifiants marchand disponibles :
    - settings.ORANGE_MONEY_MERCHANT_KEY
    - settings.ORANGE_MONEY_API_URL
    - vérification de signature du callback
    """

    def initiate_payment(self, paiement) -> str:
        import requests

        api_url = settings.ORANGE_MONEY_API_URL
        merchant_key = settings.ORANGE_MONEY_MERCHANT_KEY
        if not api_url or not merchant_key:
            raise RuntimeError(
                "OrangeMoneyGateway nécessite ORANGE_MONEY_API_URL et ORANGE_MONEY_MERCHANT_KEY dans le .env"
            )

        # TODO: adapter au format exact de l'API Orange Money Cameroun (Web Payment API).
        response = requests.post(
            api_url,
            json={
                "merchant_key": merchant_key,
                "amount": str(paiement.montant),
                "order_id": paiement.commande_id,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("reference_transaction", "")

    def handle_callback(self, payload: dict) -> tuple[str, bool]:
        # TODO: vérifier la signature/authenticité du callback avant de faire confiance au payload.
        reference = payload.get("reference_transaction", "")
        succes = payload.get("status") == "SUCCESS"
        return reference, succes


def get_payment_gateway() -> PaymentGateway:
    backend_name = getattr(settings, "PAYMENT_GATEWAY", "mock")
    if backend_name == "orange_money":
        return OrangeMoneyGateway()
    return MockOrangeMoneyGateway()
