# Application Android (APK) — état et étapes restantes

Objectif : produire un fichier `.apk` de l'application FRPS Nord, à distribuer
directement aux formations sanitaires (WhatsApp / lien de téléchargement), sans
passer par le Play Store.

La technique retenue est une **TWA** (*Trusted Web Activity*) : l'APK est une
enveloppe Android très fine autour de la PWA déjà en ligne sur `frpsno.com`.
L'application affiche le site en plein écran, sans barre d'adresse. Elle
**n'apporte aucune capacité hors connexion supplémentaire** par rapport à la PWA
installée depuis le navigateur — c'est le même moteur, le même service worker.

## Déjà fait (2026-08-17)

- **Chaîne de compilation installée** sur la machine de développement :
  - Bubblewrap CLI (`npm install -g @bubblewrap/cli`)
  - JDK 17 dans `C:\Users\DELL\.bubblewrap\jdk\jdk-17.0.11+9`
  - SDK Android dans `C:\Users\DELL\.bubblewrap\android_sdk`
  - chemins enregistrés dans `C:\Users\DELL\.bubblewrap\config.json`
- **Projet Android généré** dans `C:\Users\DELL\Documents\Project claude online\frps-apk\`
  (volontairement **hors du dépôt Git** : ce sont des fichiers de build, régénérables).
  Sa configuration est `twa-manifest.json` : identifiant `com.frpsno.commande`,
  nom « FRPS Nord en Ligne », lanceur « FRPS-NO », thème vert `#0F9D58`, icônes
  reprises du manifeste en ligne, orientation portrait, version 1.0.0.
- **Chaîne vérifiée** : Gradle 8.11.1 démarre correctement avec le JDK 17 depuis
  PowerShell, et le projet généré porte bien `applicationId com.frpsno.commande`,
  `hostName frpsno.com`, `launchUrl /`, version 1.0.0. Il ne manque que les
  `build-tools`, bloqués par la licence de l'étape 1.
- **Côté serveur Django** : la route `/.well-known/assetlinks.json` existe
  (`frps_project/pwa.py`). Elle renvoie 404 tant que l'empreinte du certificat de
  signature n'est pas connue — voir étape 3.

## Étapes restantes (à faire par toi)

Deux d'entre elles n'ont volontairement pas été faites à ta place : accepter une
licence juridique en ton nom, et choisir un mot de passe de signature.

### Étape 1 — accepter les licences du SDK Android (une seule fois)

Les outils de compilation ne s'installent pas tant que la licence Google n'est pas
acceptée. Ouvre **PowerShell** et lance :

```bash
$env:JAVA_HOME = "$env:USERPROFILE\.bubblewrap\jdk\jdk-17.0.11+9"; & "$env:USERPROFILE\.bubblewrap\android_sdk\tools\bin\sdkmanager.bat" --sdk_root="$env:USERPROFILE\.bubblewrap\android_sdk" --licenses
```

Les deux ajouts sont indispensables, chacun corrigeant une erreur distincte :

- sans `JAVA_HOME`, `sdkmanager` ne connaît pas le JDK installé par Bubblewrap et
  s'arrête sur `ERROR: JAVA_HOME is not set` ;
- sans `--sdk_root`, il n'arrive pas à déduire l'emplacement du SDK et échoue sur
  `Warning: Could not create settings` suivi d'une `IllegalArgumentException`.

Réponds `y` à chaque question. C'est un accord juridique entre Google et toi, d'où
le fait que je ne l'aie pas accepté moi-même.

### Étape 2 — créer la clé de signature et construire l'APK

```bash
$env:JAVA_HOME = "$env:USERPROFILE\.bubblewrap\jdk\jdk-17.0.11+9"; cd "C:\Users\DELL\Documents\Project claude online\frps-apk"; bubblewrap build
```

Bubblewrap constate que `android.keystore` n'existe pas et propose de le créer. Il
demande alors **un mot de passe, à choisir par toi** (deux fois : magasin de clés
et clé). Note-le et conserve-le.

> **Le fichier `android.keystore` et son mot de passe sont irremplaçables.**
> Perdus, tu ne peux plus publier de mise à jour de l'application : les FOSA
> devraient désinstaller puis réinstaller une application considérée comme
> différente par Android. Sauvegarde-les ailleurs que sur cette machine.

Le build produit `app-release-signed.apk` dans le même dossier — c'est le fichier
à envoyer aux FOSA.

### Étape 3 — publier l'empreinte du certificat

Sans cette étape, l'application s'ouvrira **avec la barre d'adresse du navigateur
visible** au lieu d'un vrai plein écran. Récupère l'empreinte SHA-256 :

```bash
cd "C:\Users\DELL\Documents\Project claude online\frps-apk"; bubblewrap fingerprint list
```

Puis, dans le tableau de bord Render, ajoute la variable d'environnement :

- `ANDROID_SHA256_FINGERPRINT` = l'empreinte SHA-256 (format `AB:CD:EF:...`)

Après redéploiement, vérifie que `https://frpsno.com/.well-known/assetlinks.json`
répond bien (elle renvoie 404 tant que la variable est vide). Réinstalle ensuite
l'APK sur un téléphone pour constater la disparition de la barre d'adresse.

## Distribution aux FOSA

Envoie `app-release-signed.apk` par WhatsApp ou mets-le en téléchargement. À la
première installation, le téléphone demandera d'autoriser « installer des
applications inconnues » pour la source utilisée — c'est normal hors Play Store.

## Mises à jour

L'APK n'étant qu'une enveloppe, **toute évolution du site est immédiatement visible
dans l'application sans rien réinstaller**. Reconstruire l'APK n'est nécessaire que
pour changer le nom, l'icône, les couleurs ou la configuration Android. Dans ce cas :
incrémenter `appVersion` et `appVersionCode` dans `twa-manifest.json`, relancer
`bubblewrap update` puis `bubblewrap build`, et rediffuser le fichier.

## Écueils rencontrés

- **Les commandes Bubblewrap interactives ne peuvent pas être automatisées** : la
  bibliothèque de questions utilisée recrée un flux d'entrée à chaque question, si
  bien qu'alimenter les réponses par un tube n'en fait passer qu'une seule. C'est
  pourquoi `twa-manifest.json` a été écrit à la main puis appliqué avec
  `bubblewrap update`, qui, lui, ne pose aucune question.
- **Lancer le build depuis Git Bash échoue** (`'gradlew.bat' n'est pas reconnu`).
  Utiliser PowerShell ou l'invite de commandes Windows.
