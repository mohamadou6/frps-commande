from abc import ABC, abstractmethod
from decimal import Decimal

from django.conf import settings


class StockConnector(ABC):
    """Source du stock. Retourne une liste de dicts avec les clés :
    code_sage, nom, unite, prix_unitaire, stock_disponible.
    """

    @abstractmethod
    def fetch_produits(self) -> list[dict]:
        raise NotImplementedError


class MockStockConnector(StockConnector):
    """Données d'exemple, utilisées tant que l'accès au SQL Server du FRPS
    n'est pas disponible. Permet de développer et tester tout le parcours.
    """

    def fetch_produits(self) -> list[dict]:
        return [
            {
                "code_sage": "MED-001",
                "nom": "Paracétamol 500mg (boîte de 100)",
                "unite": "boîte",
                "prix_unitaire": Decimal("1500"),
                "stock_disponible": 240,
            },
            {
                "code_sage": "MED-002",
                "nom": "Amoxicilline 500mg (boîte de 100)",
                "unite": "boîte",
                "prix_unitaire": Decimal("3200"),
                "stock_disponible": 120,
            },
            {
                "code_sage": "MED-003",
                "nom": "Sérum salé 0,9% (flacon 500ml)",
                "unite": "flacon",
                "prix_unitaire": Decimal("800"),
                "stock_disponible": 500,
            },
            {
                "code_sage": "MED-004",
                "nom": "Artéméther/Luméfantrine 20/120mg",
                "unite": "boîte",
                "prix_unitaire": Decimal("2500"),
                "stock_disponible": 0,
            },
            {
                "code_sage": "MED-005",
                "nom": "Gants d'examen latex (boîte de 100)",
                "unite": "boîte",
                "prix_unitaire": Decimal("4000"),
                "stock_disponible": 75,
            },
        ]


class SageSQLServerConnector(StockConnector):
    """Connexion en lecture seule au SQL Server du FRPS (Sage Gescom).

    Nécessite dans le .env : SQLSERVER_HOST, SQLSERVER_DB, SQLSERVER_USER,
    SQLSERVER_PASSWORD, SQLSERVER_DRIVER.

    Utilise F_ARTICLE (référentiel articles) et F_ARTSTOCK (stock par dépôt,
    sommé tous dépôts confondus). F_ARTPRIX existe mais est vide côté FRPS,
    ne pas s'en servir pour le prix. AR_PrixTTC est un indicateur (smallint,
    toujours à 0 côté FRPS), pas un prix : le prix de vente réel est
    AR_PrixVen.
    """

    def fetch_produits(self) -> list[dict]:
        import pyodbc

        conn_str = (
            f"DRIVER={{{settings.SQLSERVER_DRIVER}}};"
            f"SERVER={settings.SQLSERVER_HOST};"
            f"DATABASE={settings.SQLSERVER_DB};"
            f"UID={settings.SQLSERVER_USER};"
            f"PWD={settings.SQLSERVER_PASSWORD};"
        )
        query = """
            SELECT a.AR_Ref AS code_sage, a.AR_Design AS nom, a.AR_UniteVen AS unite,
                   a.AR_PrixVen AS prix_unitaire,
                   ISNULL(s.stock_disponible, 0) AS stock_disponible
            FROM F_ARTICLE a
            LEFT JOIN (
                SELECT AR_Ref, SUM(AS_QteSto) AS stock_disponible
                FROM F_ARTSTOCK
                GROUP BY AR_Ref
            ) s ON s.AR_Ref = a.AR_Ref
            WHERE a.AR_Sommeil = 0
        """

        produits = []
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                produits.append(dict(zip(columns, row)))
        return produits


def get_stock_connector() -> StockConnector:
    backend_name = getattr(settings, "STOCK_CONNECTOR_BACKEND", "mock")
    if backend_name == "sage_sql_server":
        return SageSQLServerConnector()
    return MockStockConnector()
