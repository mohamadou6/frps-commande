"""Vues de l'enveloppe PWA (application installable sur mobile).

Le service worker et le manifeste sont rendus par Django plutôt que servis comme
fichiers statiques, pour deux raisons :
- `{% static %}` doit résoudre les noms de fichiers hachés par
  `CompressedManifestStaticFilesStorage` en production ;
- le service worker doit être servi depuis la racine du site (`/sw.js`) pour
  contrôler l'ensemble des pages, ce qu'un fichier sous `/static/` ne permet pas.
"""

from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET


@require_GET
@cache_control(no_cache=True, max_age=0)
def service_worker(request):
    """`no-cache` : le navigateur doit revalider le fichier pour voir les mises à jour."""
    return render(request, "pwa/sw.js", content_type="application/javascript")


@require_GET
def manifeste(request):
    return render(request, "pwa/manifest.webmanifest", content_type="application/manifest+json")


@require_GET
def hors_ligne(request):
    """Page de repli affichée quand une page non encore consultée est demandée sans réseau.

    Volontairement autonome (n'étend pas `base.html`) : elle est mise en cache à
    l'installation du service worker et ne doit donc contenir aucune donnée
    propre à un utilisateur.
    """
    return render(request, "pwa/hors_ligne.html")
