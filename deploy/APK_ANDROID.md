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

### Étape 2a — créer la clé de signature

`bubblewrap build` demande bien un mot de passe, mais **ne crée pas** le fichier
`android.keystore` : c'est `bubblewrap init` qui s'en charge normalement, or cette
étape a été contournée (voir « Écueils » plus bas). La clé se crée donc à part,
avec `keytool`, livré avec le JDK :

```bash
cd "C:\Users\DELL\Documents\Project claude online\frps-apk"; & "$env:USERPROFILE\.bubblewrap\jdk\jdk-17.0.11+9\bin\keytool.exe" -genkeypair -v -keystore android.keystore -alias android -keyalg RSA -keysize 2048 -validity 10000
```

Questions posées, dans l'ordre : mot de passe (deux fois), nom, unité
organisationnelle, organisation, ville, région, code pays sur 2 lettres, puis une
confirmation, puis le mot de passe de la clé (Entrée pour reprendre le même).
Réponses possibles : `FRPS Nord`, `GIP-FRPS NORD`, `Garoua`, `Nord`, `CM`. Ces
valeurs n'ont aucune conséquence fonctionnelle.

Le nom de fichier `android.keystore` et l'alias `android` doivent être respectés :
ce sont ceux déclarés dans `twa-manifest.json`.

### Étape 2b — construire l'APK signé

```bash
$env:JAVA_HOME = "$env:USERPROFILE\.bubblewrap\jdk\jdk-17.0.11+9"; $env:NoDefaultCurrentDirectoryInExePath = $null; cd "C:\Users\DELL\Documents\Project claude online\frps-apk"; & "$env:APPDATA\npm\bubblewrap.cmd" build --skipPwaValidation
```

Deux précautions supplémentaires dans cette commande :

- **appel direct du script Node, en chemins absolus** : `bubblewrap` seul échoue si
  la fenêtre PowerShell a été ouverte avant l'installation (dossier des commandes
  npm absent du `PATH`), et le raccourci `bubblewrap.cmd` a lui aussi été rejeté
  par `CommandNotFoundException` sur cette machine alors que le fichier existe
  bien — vraisemblablement une restriction d'exécution des `.cmd`. Passer par
  `node.exe` avec le chemin du script contourne les deux ;
- **`--skipPwaValidation`** : sans cette option, Bubblewrap soumet le site à l'API
  Google PageSpeed Insights, qui répond couramment `429 Too Many Requests` et fait
  échouer le build. Cette validation ne conditionne en rien la qualité de l'APK.

`NoDefaultCurrentDirectoryInExePath` vaut `1` sur cette machine, ce qui empêche
`cmd` d'exécuter un programme du dossier courant. Or Bubblewrap lance
`gradlew.bat` sans préfixe de chemin : sans cette neutralisation, le build échoue
sur `'gradlew.bat' n'est pas reconnu`. La variable n'est modifiée que pour la
session PowerShell en cours, rien n'est changé sur le système.

Cette commande **sans** `--skipSigning` a été validée dans sa version non signée :
le build aboutit et produit `app-release-unsigned-aligned.apk` (1,3 Mo) ainsi que
le bundle `app/build/outputs/bundle/release/app-release.aab`. Seule l'étape de
signature reste donc à faire.

Bubblewrap constate que `android.keystore` n'existe pas et propose de le créer. Il
demande alors **un mot de passe, à choisir par toi** (deux fois : magasin de clés
et clé). Note-le et conserve-le.

> **Le fichier `android.keystore` et son mot de passe sont irremplaçables.**
> Perdus, tu ne peux plus publier de mise à jour de l'application : les FOSA
> devraient désinstaller puis réinstaller une application considérée comme
> différente par Android. Sauvegarde-les ailleurs que sur cette machine.

Le build produit `app-release-signed.apk` dans le même dossier — c'est le fichier
à envoyer aux FOSA.

### Étapes 1, 2a et 2b : FAITES le 2026-08-17

`app-release-signed.apk` (1,4 Mo) et `app-release-bundle.aab` ont été produits.
Signature vérifiée avec `apksigner verify --print-certs` :
`CN=MOHAMADOU IBRAHIMA, OU=FRPS-NO, O=FRPS-NO, L=GAROUA, ST=NORD, C=CM`.

La clé a été **recréée** le 2026-08-17 : la première portait `C=NO` au lieu de
`CM`, le code pays étant gravé dans le certificat et non modifiable. L'opération a
été faite avant toute distribution, donc sans conséquence — recréer la clé après
diffusion aurait obligé les FOSA à désinstaller puis réinstaller l'application,
Android considérant une signature différente comme une application différente.
L'ancienne clé a été supprimée : `frps-apk/android.keystore` est désormais la
seule, et il n'y a plus d'ambiguïté sur le fichier à sauvegarder.

Empreinte SHA-256 du certificat, au format attendu par `assetlinks.json` :

```
D6:3F:62:59:0F:FB:49:09:E5:0B:F3:5D:F3:CF:A0:C8:35:A2:E0:5D:23:1F:70:4B:63:52:F5:90:1D:50:E9:E1
```

Elle se retrouve à tout moment sans mot de passe, à partir de l'APK :

```bash
cd "C:\Users\DELL\Documents\Project claude online\frps-apk"; & "$env:USERPROFILE\.bubblewrap\android_sdk\build-tools\35.0.0\apksigner.bat" verify --print-certs .\app-release-signed.apk
```

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
- **`'gradlew.bat' n'est pas reconnu`** : ce n'est pas un problème de shell (l'erreur
  se produit aussi depuis PowerShell) mais la variable d'environnement
  `NoDefaultCurrentDirectoryInExePath=1`, qui interdit à `cmd` d'exécuter un
  programme du dossier courant. Voir l'étape 2.
- **`Could not initialize native services` de Gradle** : erreur transitoire observée
  une fois, causée par un démon Gradle concurrent resté d'une tentative précédente.
  Relancer suffit.
- **Ne pas filtrer la sortie du build avec `Select-Object -Last N`** : en cas
  d'échec, seule la fin de la pile d'appels est conservée et le message de cause
  disparaît. Rediriger vers un fichier (`| Out-File build.log`) puis le lire.
