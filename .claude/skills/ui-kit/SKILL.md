---
name: ui-kit
description: Charte visuelle et composants de l'application FRPS — palette et mode sombre, cartes, titres, tableaux, boutons, barre de navigation et onglets du bas, messages en bulles, barre de chargement, règles de formatage des montants. À utiliser avant d'écrire ou de modifier un gabarit HTML de `commande-frps`, d'ajouter une page, un tableau, un formulaire ou un encart de chiffres, pour rester cohérent avec l'existant sans relire plusieurs gabarits.
---

# Charte visuelle FRPS

Tout le style est **centralisé dans `accounts/static/css/app.css`** (et non plus dans un
bloc `<style>` de `base.html`, depuis le 2026-10-22) : le fichier est téléchargé une fois
puis servi par le cache du service worker. Les comportements communs sont dans
**`accounts/static/js/app.js`**. Un gabarit de page ne définit ni style ni script : il
assemble des classes. Si un besoin revient deux fois, il va dans `app.css` / `app.js`.

## Couleurs : toujours par variable

Les couleurs passent par des variables CSS (`--app-…`) redéfinies pour le **mode sombre**,
qui suit le réglage du téléphone (attribut `data-bs-theme` posé par le petit script du
`<head>` de `base.html` ; Bootstrap 5.3 gère lui-même champs, menus et tableaux).
**Ne jamais écrire une couleur en dur** dans une règle de surface ou de texte : elle
resterait claire en mode sombre. Pour un badge neutre, `bg-body-secondary
text-body-secondary`, pas `bg-light text-dark`.

| Variable | Rôle | Clair |
|---|---|---|
| `--app-vert` / `--app-vert-fonce` | marque, boutons | `#0f9d58` / `#0b7a45` |
| `--app-vert-actif` | texte vert lisible (s'éclaircit en sombre) | `#0b7a45` |
| `--app-fond` | fond de page (jamais blanc pur) | `#f4f8f5` |
| `--app-surface` | cartes, tableaux, panneaux | `#fff` |
| `--app-texte` / `--app-titre` / `--app-texte-2` | texte, titres, secondaire | `#17251d` / `#12321f` / `#6c8a79` |
| `--app-bordure` / `--app-bordure-2` | bordures, en-têtes de tableau | `#e6efe9` / `#dbe9e0` |
| `--app-teinte-vert` / `-bleu` / `-rouge` | fonds doux (succès, info, erreur) | |
| `--app-ombre` | signature des surfaces | |

Signature commune à toutes les surfaces : `border-radius: 16px` et `box-shadow: var(--app-ombre)`.
Les graphiques Chart.js lisent le thème au chargement (`NEUTRES` dans `graphiques.js`).

## Composants

- **`.app-carte`** — surface standard. **`.app-titre`** (liseré vert en `::before`, ne pas
  le dessiner à la main) puis **`.app-sous-titre`**.
- **`.app-bandeau`** — bandeau vert d'en-tête (catalogue, tableau de bord) :
  `.app-bandeau-titre`, `.app-bandeau-texte`, puis une recherche ou un formulaire (champs
  blancs, bouton `btn-light`). Réservé aux pages principales ; les autres gardent `.app-titre`.
- **`.table-responsive`** — enveloppe obligatoire de tout tableau : boîte et défilement
  horizontal, indispensable sur téléphone.
- **`.card`** / **`a.card`** — cartes-liens, léger soulèvement au survol (neutralisé au doigt).
- **`.border.rounded-3`** — encarts de chiffres. Dans une `.row > .col`, ils apparaissent
  l'un après l'autre ; un `.fw-bold` qui ne contient **qu'un nombre** (suivi ou non de
  `FCFA` ou `%`) défile de 0 à sa valeur, puis le texte d'origine est remis au caractère près.
- **Barre de navigation** (`.app-navbar`, `navbar-expand-xl`) : **sous 1 200 px**, en-tête
  compact (« FRPS-NO », initiale du compte à droite) et **onglets en bas**
  (`.barre-onglets`, `aria-current="page"` sur l'onglet actif) ; le menu complet monte du
  bas en panneau. Un lien déjà présent dans les onglets porte `doublon-onglets` pour ne
  pas être répété dans le panneau. Titre long à partir de 1 200 px pour une FOSA,
  1 600 px pour le personnel (`nav-personnel`), sinon la barre déborde.
- **Messages Django** : affichés en **bulles** (`.zone-toasts`, toujours présente dans
  `base.html`). Succès et info s'effacent seuls, erreurs et avertissements restent
  jusqu'à ce qu'on les ferme. Depuis un script : `window.frpsToast(texte, "success"|"info"|"warning"|"danger")`.
  Ne pas réafficher les messages dans une page.
- **Barre de chargement** : démarre seule au clic sur un lien et à l'envoi d'un
  formulaire (sauf téléchargements, exports, nouvel onglet). Pour une navigation
  déclenchée en JavaScript : `window.frpsChargement()` avant de changer de page.
- **Transitions entre pages** : fondu CSS (`@view-transition`), sans JavaScript.
- **Ordinateur (≥ 1 200 px)** : barre du haut fixe, page en cours surlignée
  (`aria-current="page"` sur les liens, classe `actif` sur les menus déroulants). Fiches
  du catalogue et cartes-liens qui apparaissent au défilement (CSS `animation-timeline`).
  Au catalogue, la touche « / » mène à la recherche et Échap l'efface.

## Règles à ne pas défaire

**Bootstrap est hébergé en local**, jamais via un CDN : sur le réseau intermittent des
FOSA, un CDN injoignable affichait l'application sans aucune mise en forme.

**`btn-primary` est redéfini en vert.** Utiliser `btn-primary`, surtout pas `btn-success`.
**Le bouton « Ajouter » du catalogue reste bleu** (`.btn-ajouter`), choix confirmé le 2026-10-22.

**Aucune image décorative, aucune police téléchargée** — tout en CSS. Les icônes sont des
**emoji** (💊 📦 🛒 🧾 📊 🔔 💳 🏥 ⭐ 💰), pas une bibliothèque d'icônes : zéro octet à télécharger.

**Animations** : toutes coupées par le réglage « réduire les animations » du téléphone
(bloc `prefers-reduced-motion` en fin d'`app.css`). Une nouvelle animation n'a rien à
ajouter pour en profiter.

**Catalogue** : `content-visibility: auto` sur les fiches (`.catalogue-grille > .col`) —
le navigateur ne calcule que les fiches visibles. La **recherche instantanée** (`app.js`)
reproduit `_mots_recherches` / `_nom_contient` de `catalogue/views.py` : **toute
modification de ces règles se fait aux deux endroits** (vérifié identique sur les 1 249
produits du bac à sable le 2026-10-22).

**Mobile d'abord.** Toute nouvelle page se vérifie à 375 px de large, en clair et en sombre.

**Montants : deux régimes, ne pas uniformiser.** Le **prix unitaire** et le **total
d'une ligne** gardent leurs décimales (`floatformat:"2"`, `formater_prix`). **Tout total
général** — commande, payé, solde, statistiques — s'affiche sans décimales
(`floatformat:"0"`, `formater_montant`) ; il est d'ailleurs déjà entier en base.

## Ajouter une page

```html
{% extends "base.html" %}
{% block title %}Titre de l'onglet{% endblock %}
{% block content %}
<h1 class="app-titre">Titre de la page</h1>
<p class="app-sous-titre">Une phrase de contexte.</p>

<div class="table-responsive">
  <table class="table align-middle">
    ...
  </table>
</div>
{% endblock %}
```

Le conteneur (`container`) est fourni par `base.html` ; le surcharger via
`{% block container_class %}` seulement pour une page qui a besoin de toute la largeur.
`{% block body_class %}` pose une classe sur `<body>` (ex. `page-connexion`).

**Nouveau fichier statique** (CSS, JS, image) : l'ajouter à `RESSOURCES_COQUILLE` dans
`templates/pwa/sw.js` s'il sert à toutes les pages, et relancer `collectstatic` en local
— les tests lisent le manifeste de `staticfiles/` et échouent tous (« Missing staticfiles
manifest entry ») tant que le fichier n'y figure pas.

## Bandeaux PWA

`base.html` porte deux bandeaux conditionnels — installation de l'application, et
activation des notifications (personnel FRPS uniquement). L'installation est pilotée par
`app.js`, les notifications par le script resté dans `base.html` (il a besoin de la clé
VAPID et du jeton CSRF). Ne pas les dupliquer dans une page : pour toute modification de
leur comportement, voir la skill `pwa-django`.
