"""Sert l'application en production via Waitress (WSGI, fonctionne sur Windows).

Usage : venv\\Scripts\\python.exe deploy\\run_waitress.py
Écoute sur 127.0.0.1:8000 - le tunnel Cloudflare (cloudflared) route le trafic
public HTTPS vers cette adresse locale, donc pas besoin d'écouter sur 0.0.0.0.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frps_project.settings")

import django  # noqa: E402

django.setup()

from waitress import serve  # noqa: E402
from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()

if __name__ == "__main__":
    serve(application, host="127.0.0.1", port=8000, threads=8)
