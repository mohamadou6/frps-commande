# Déploiement en production - Render.com

Remplace l'ancien déploiement Windows Server + Cloudflare Tunnel (voir
`deploy/DEPLOYMENT.md`, conservé pour référence historique mais **obsolète**).

Domaine cible : **frpsno.com** (DNS à repointer une fois le service Render en ligne,
voir étape 6).

## Ce que fait `render.yaml`

Le fichier `render.yaml` à la racine du projet est un "Blueprint" Render : il décrit
un service web Python + une base PostgreSQL gérée. Render lit ce fichier
automatiquement quand on connecte le repo.

- Build : `pip install -r requirements.txt && collectstatic && migrate && ensure_admin`
- Start : `gunicorn frps_project.wsgi:application`
- `STOCK_CONNECTOR_BACKEND=mock` et `PAYMENT_GATEWAY=mock` (conforme aux décisions
  actées : pas de synchro Sage automatique, pas d'Orange Money réel pour l'instant)
- `SMS_BACKEND=twilio` : les identifiants Twilio sont marqués `sync: false`, donc à
  saisir manuellement dans le dashboard Render (jamais commités en clair)

`ensure_admin` est une commande custom (`accounts/management/commands/ensure_admin.py`)
qui crée le compte admin FRPS à partir de `DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD`
si ces variables sont définies et que le compte n'existe pas encore — idempotent,
sans risque à chaque redéploiement (contrairement à `createsuperuser` qui plante si
le compte existe déjà, et qui de toute façon ne peut pas se lancer en interactif
pendant un build Render).

## Étapes

### 1. Compte Render + connexion du repo (à faire par toi)

1. Créer un compte sur [render.com](https://render.com) (gratuit pour démarrer)
2. Pousser ce projet sur un repo GitHub (privé de préférence)
3. Dans Render : **New > Blueprint**, connecter le repo GitHub → Render détecte
   `render.yaml` et propose de créer le service web + la base Postgres

### 2. Variables d'environnement à saisir manuellement dans le dashboard Render

Ces variables sont marquées `sync: false` dans `render.yaml`, donc pas pré-remplies :

| Variable | Valeur |
|---|---|
| `TWILIO_ACCOUNT_SID` | celui déjà utilisé en dev (voir `.env` actuel ou console.twilio.com) |
| `TWILIO_AUTH_TOKEN` | idem |
| `TWILIO_SMS_FROM` | idem |
| `DJANGO_SUPERUSER_USERNAME` | ex: `admin` |
| `DJANGO_SUPERUSER_EMAIL` | ton email |
| `DJANGO_SUPERUSER_PASSWORD` | mot de passe fort — à changer ensuite si besoin via l'admin Django |

Après le premier déploiement réussi, tu peux supprimer les 3 variables
`DJANGO_SUPERUSER_*` du dashboard (le compte admin est créé, plus besoin qu'elles
traînent en clair) — `ensure_admin` ne fera simplement plus rien au déploiement
suivant si elles sont absentes.

### 3. Vérifier `ALLOWED_HOSTS` / `PUBLIC_BASE_URL`

`render.yaml` pré-remplit `frps-commande.onrender.com`, mais Render peut attribuer un
nom légèrement différent si celui-ci est déjà pris. Une fois le service créé, vérifie
l'URL réelle donnée par Render et corrige au besoin les variables `ALLOWED_HOSTS` et
`PUBLIC_BASE_URL` dans le dashboard (Environment).

### 4. Créer les comptes personnel FRPS

Une fois le site accessible, se connecter à `/admin/` avec le compte superuser créé
à l'étape 2, puis créer les comptes `personnel_stock` et `personnel_comptabilite`
avec leurs vrais numéros de téléphone — **indispensable pour que les SMS partent**
(voir le gotcha dans `CLAUDE.md` : aucun SMS n'est envoyé, sans erreur, si aucun
compte du rôle concerné n'a de téléphone renseigné).

Éditer aussi le catalogue (`/admin/catalogue/...`) : prix et stock réels à saisir
manuellement après consultation de Sage (décision actée, pas de synchro auto).

### 5. Vérification

Ouvrir l'URL Render (`https://frps-commande.onrender.com` ou équivalent) depuis un
navigateur externe, tester : connexion, catalogue, panier → commande → paiement,
réception du SMS de notification.

### 6. Domaine frpsno.com

Dans Render : **Settings > Custom Domains** sur le service web, ajouter
`frpsno.com` et `www.frpsno.com`, puis suivre les instructions Render pour les
enregistrements DNS (CNAME/A selon le cas).

Chez le registrar du domaine (Cloudflare) : **supprimer les anciens enregistrements
CNAME** qui pointaient vers le tunnel Cloudflare démantelé, et créer les nouveaux
enregistrements demandés par Render.

Une fois le domaine actif, mettre à jour `ALLOWED_HOSTS` et `PUBLIC_BASE_URL` dans
le dashboard Render pour inclure `frpsno.com` (et retirer l'URL `onrender.com` si tu
veux forcer l'accès uniquement via le domaine final — optionnel).

## Note sur le plan gratuit Render

Le plan `free` (web service + Postgres) suffit pour valider le déploiement, mais :
- Le service web gratuit se met en veille après 15 min d'inactivité (premier
  chargement lent après une veille)
- La base Postgres gratuite est supprimée après 90 jours si non upgradée

Passer sur un plan payant avant la mise en usage réel avec les FOSA, pour éviter la
veille et la suppression automatique de la base.
