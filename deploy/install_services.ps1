# Script d'installation des services Windows pour l'application FRPS.
# À exécuter en PowerShell (Administrateur) sur le serveur de production, une fois :
#   - Python + venv + dépendances installés (venv\Scripts\pip install -r requirements.txt)
#   - Le fichier .env de production en place (voir production.env.example)
#   - `python manage.py migrate` et `python manage.py collectstatic --noinput` exécutés
#
# Adapter $ProjectDir si le projet n'est pas dans ce chemin.

$ProjectDir = "C:\FRPS\commande-frps"
$PythonExe = "$ProjectDir\venv\Scripts\python.exe"
$WaitressScript = "$ProjectDir\deploy\run_waitress.py"

Write-Host "1. Installation de NSSM et cloudflared (via winget)..."
winget install --id NSSM.NSSM -e --accept-package-agreements --accept-source-agreements
winget install --id Cloudflare.cloudflared -e --accept-package-agreements --accept-source-agreements

Write-Host "2. Enregistrement du service Django (Waitress) via NSSM..."
nssm install FRPSCommande $PythonExe $WaitressScript
nssm set FRPSCommande AppDirectory $ProjectDir
nssm set FRPSCommande Start SERVICE_AUTO_START
nssm set FRPSCommande AppStdout "$ProjectDir\deploy\logs\waitress.log"
nssm set FRPSCommande AppStderr "$ProjectDir\deploy\logs\waitress-error.log"
New-Item -ItemType Directory -Force -Path "$ProjectDir\deploy\logs" | Out-Null
nssm start FRPSCommande

Write-Host ""
Write-Host "3. Tunnel Cloudflare : étapes manuelles restantes (nécessitent ton compte Cloudflare) :"
Write-Host "   a. cloudflared tunnel login"
Write-Host "   b. cloudflared tunnel create frps-commande"
Write-Host "   c. cloudflared tunnel route dns frps-commande frpsno.com"
Write-Host "   d. Configurer deploy\cloudflared-config.yml (voir le modèle fourni) avec l'ID du tunnel créé"
Write-Host "   e. cloudflared service install"
Write-Host ""
Write-Host "Une fois fait, vérifier : Get-Service FRPSCommande, Get-Service cloudflared"
