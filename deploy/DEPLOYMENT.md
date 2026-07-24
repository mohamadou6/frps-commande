# Déploiement en production - Serveur Windows Server au FRPS

Domaine : **frpsno.com** (enregistré sur Cloudflare Registrar).
Architecture : serveur Windows physique au FRPS, sur le même réseau que le SQL Server
Sage Gescom (connexion directe, pas de VPN nécessaire), exposé sur Internet via un
tunnel Cloudflare (pas besoin d'IP publique).

## Prérequis sur le serveur Windows

1. **Python 3.12** installé (`python --version` pour vérifier)
2. **PostgreSQL** installé et une base créée pour l'application
   - Créer un utilisateur et une base : `CREATE DATABASE frps_commande; CREATE USER frps_user WITH PASSWORD '...'; GRANT ALL ON DATABASE frps_commande TO frps_user;`
3. **Driver ODBC SQL Server** installé si pas déjà présent (nécessaire pour la connexion à Sage Gescom) : "ODBC Driver 17 for SQL Server" (téléchargeable chez Microsoft)
4. Le code du projet copié sur le serveur (ex: `C:\FRPS\commande-frps`)

## Étapes

### 1. Environnement Python

```powershell
cd C:\FRPS\commande-frps
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

### 2. Configuration

Copier `deploy\production.env.example` vers `.env` à la racine du projet, puis renseigner :
- `SECRET_KEY` : générer une nouvelle clé (`venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `DATABASE_URL` : identifiants PostgreSQL créés ci-dessus
- `SQLSERVER_HOST` / `SQLSERVER_DB` / `SQLSERVER_USER` / `SQLSERVER_PASSWORD` : accès au SQL Server Sage Gescom du FRPS (à demander à l'administrateur système/DBA du FRPS)
- `ALLOWED_HOSTS` : `frpsno.com,www.frpsno.com`
- `PUBLIC_BASE_URL` : `https://frpsno.com`
- Les identifiants Twilio (SMS) déjà utilisés en dev peuvent être repris tels quels

**Important** : la requête SQL dans `stock_sync/connectors.py` (classe `SageSQLServerConnector`)
contient un `TODO` — les noms de tables/colonnes réels de Sage Gescom (`dbo.ARTICLES` etc.
dans le squelette actuel) doivent être confirmés et adaptés avec l'administrateur Sage du FRPS
avant de passer `STOCK_CONNECTOR_BACKEND=sage_sql_server`.

**Compte SQL Server en lecture seule** : ne jamais utiliser un compte SQL Server avec des
droits d'écriture pour `SQLSERVER_USER`. Faire exécuter par l'administrateur SQL Server du
FRPS le script `deploy\sql\create_readonly_user.sql`, qui crée un compte dédié
(`frps_commande_readonly`) avec uniquement des droits de lecture — garantit qu'aucun bug
applicatif ne pourrait modifier la base Sage, même par erreur.

### 3. Base de données et fichiers statiques

```powershell
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py collectstatic --noinput
venv\Scripts\python.exe manage.py createsuperuser
```

### 4. Services Windows (démarrage automatique)

Exécuter en PowerShell **Administrateur** :

```powershell
deploy\install_services.ps1
```

Ce script installe NSSM (gestionnaire de services) et cloudflared, puis enregistre
l'application Django comme service Windows (`FRPSCommande`, démarrage automatique,
redémarre seul en cas de plantage).

### 5. Tunnel Cloudflare (accès public sans IP fixe)

Étapes manuelles (nécessitent le compte Cloudflare) :

```powershell
cloudflared tunnel login
cloudflared tunnel create frps-commande
cloudflared tunnel route dns frps-commande frpsno.com
```

Copier `deploy\cloudflared-config.yml.example` vers `deploy\cloudflared-config.yml`,
renseigner l'ID du tunnel et le chemin du fichier credentials (affichés par la commande
`create` ci-dessus), puis :

```powershell
cloudflared service install --config C:\FRPS\commande-frps\deploy\cloudflared-config.yml
```

### 6. Vérification

```powershell
Get-Service FRPSCommande
Get-Service cloudflared
```

Les deux doivent être "Running". Ouvrir `https://frpsno.com` depuis un navigateur
externe (pas sur le réseau du FRPS) pour confirmer l'accès public.

### 7. Synchronisation du stock (tâche planifiée)

Créer une tâche planifiée Windows (Planificateur de tâches) pour exécuter
périodiquement (ex: toutes les 15 minutes) :

```
venv\Scripts\python.exe manage.py sync_stock
```

## Ce qui reste en mock/à activer plus tard

- `PAYMENT_GATEWAY=mock` : Orange Money réel pas encore intégré (voir discussion séparée)
- `WHATSAPP_BACKEND=log` : partage WhatsApp désormais manuel côté FOSA (bouton
  "Partager par WhatsApp"), pas d'envoi automatique serveur
- `ORANGE_SMS_*` : intégration Orange CM préparée dans le code mais pas activée
  (Twilio suffit pour l'instant, cf. `notifications/backends.py`)
