"""Vues de l'enveloppe PWA (application installable sur mobile).

Le service worker et le manifeste sont rendus par Django plutôt que servis comme
fichiers statiques, pour deux raisons :
- `{% static %}` doit résoudre les noms de fichiers hachés par
  `CompressedManifestStaticFilesStorage` en production ;
- le service worker doit être servi depuis la racine du site (`/sw.js`) pour
  contrôler l'ensemble des pages, ce qu'un fichier sous `/static/` ne permet pas.
"""

import os

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

# Application Android (TWA). Ces deux valeurs sont lues dans l'environnement plutôt
# que dans settings.py pour rester avec le reste du code PWA. `read_env()` alimente
# os.environ depuis le .env local, et Render fournit de vraies variables
# d'environnement : la lecture fonctionne donc des deux côtés.
NOM_PAQUET_ANDROID = os.environ.get("ANDROID_PACKAGE_NAME", "com.frpsno.commande")
EMPREINTE_SHA256_ANDROID = os.environ.get("ANDROID_SHA256_FINGERPRINT", "")


@require_GET
@cache_control(no_cache=True, max_age=0)
def service_worker(request):
    """`no-cache` : le navigateur doit revalider le fichier pour voir les mises à jour."""
    return render(request, "pwa/sw.js", content_type="application/javascript")


@require_GET
def manifeste(request):
    return render(request, "pwa/manifest.webmanifest", content_type="application/manifest+json")


@require_GET
def assetlinks(request):
    """Lien vérifié entre le domaine et l'application Android (Digital Asset Links).

    Sans ce fichier, l'application Android s'ouvre avec la barre d'adresse du
    navigateur visible au lieu d'un vrai plein écran. Tant que l'empreinte du
    certificat de signature n'est pas renseignée, on renvoie 404 : un fichier
    présent mais invalide serait mémorisé par Android et plus difficile à corriger.
    """
    if not EMPREINTE_SHA256_ANDROID:
        raise Http404("Empreinte de signature Android non configurée")

    return JsonResponse(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": NOM_PAQUET_ANDROID,
                    "sha256_cert_fingerprints": [EMPREINTE_SHA256_ANDROID],
                },
            }
        ],
        safe=False,
    )


@require_GET
def hors_ligne(request):
    """Page de repli affichée quand une page non encore consultée est demandée sans réseau.

    Volontairement autonome (n'étend pas `base.html`) : elle est mise en cache à
    l'installation du service worker et ne doit donc contenir aucune donnée
    propre à un utilisateur.
    """
    return render(request, "pwa/hors_ligne.html")
