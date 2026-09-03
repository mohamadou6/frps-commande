---
name: ui-kit
description: Charte visuelle et composants de l'application FRPS — palette, cartes, titres, tableaux, boutons, barre de navigation, bandeaux, règles de formatage des montants. À utiliser avant d'écrire ou de modifier un gabarit HTML de `commande-frps`, d'ajouter une page, un tableau, un formulaire ou un encart de chiffres, pour rester cohérent avec l'existant sans relire plusieurs gabarits.
---

# Charte visuelle FRPS

Tout le style est **centralisé dans `commande-frps/templates/base.html`**, dans un unique
bloc `<style>`. Un gabarit de page ne définit pas de style : il assemble des classes.
Si un besoin revient deux fois, il va dans `base.html`, pas dans le gabarit.

## Palette

| Rôle | Couleur |
|---|---|
| Vert de marque (boutons, `theme-color`) | `#0f9d58` |
| Vert foncé (survol, actif, titres de navbar) | `#0b7a45` |
| Dégradé de la navbar | `#0b7a45` → `#12925a` → `#17a768` |
| Fond de page | `#f4f8f5` (jamais blanc pur : les cartes s'en détachent) |
| Texte courant / titres | `#17251d` / `#12321f` |
| Texte secondaire | `#6c8a79` |
| Bordure de carte | `#e6efe9` |
| En-tête de tableau | fond `#f0f6f2`, bordure `#dbe9e0` |

Signature commune à toutes les surfaces : `border-radius: 16px` et
`box-shadow: 0 6px 18px -14px rgba(6, 60, 35, .45)`.

## Composants

- **`.app-carte`** — surface blanche standard.
- **`.app-titre`** — titre de page ; un liseré vert vertical est ajouté en `::before`,
  ne pas le dessiner à la main. **`.app-sous-titre`** juste en dessous.
- **`.table-responsive`** — enveloppe obligatoire de tout tableau : elle fournit la
  boîte blanche *et* le défilement horizontal, indispensable sur téléphone. Styler ce
  conteneur générique évite de reprendre chaque gabarit.
- **`.card`** / **`a.card`** — cartes-liens du catalogue, avec un léger soulèvement au
  survol, neutralisé sur écran tactile.
- **`.border.rounded-3`** — encarts de chiffres (tableau de bord, écran de paiement),
  alignés sur l'aspect des cartes.
- **`.app-navbar`**, **`.user-pill`**, **`.user-avatar`** — barre de navigation et pastille
  d'identité (initiale + nom + emoji de rôle).
- **`.alert-success` / `.alert-info`** — redéfinies plus douces que les alertes Bootstrap.

## Règles à ne pas défaire

**Bootstrap est hébergé en local**, jamais via un CDN : sur le réseau intermittent des
FOSA, un CDN injoignable affichait l'application sans aucune mise en forme.

**`btn-primary` est redéfini en vert** dans `base.html`. Utiliser `btn-primary`, surtout
pas `btn-success` : une seule source pour toute l'application.

**Aucune image décorative** — tout en CSS. Les icônes sont des **emoji** (💊 📦 🛒 🧾 📊
🔔 💳 🏥 ⭐ 💰), pas une bibliothèque d'icônes : zéro octet à télécharger.

**Mobile d'abord.** La navbar se replie sous 992 px, les liens passent en pleine largeur.
Toute nouvelle page se vérifie à 375 px de large.

**Montants arrondis sans décimales** partout — gabarits, PDF, SMS — via
`floatformat:"0"` et `frps_project/formatage.py`. **Sauf le prix unitaire**, qui garde
ses décimales : choix explicite, ne pas uniformiser.

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
Les messages Django sont déjà affichés par `base.html` : ne pas les reproduire.

## Bandeaux PWA

`base.html` porte deux bandeaux conditionnels — installation de l'application, et
activation des notifications (personnel FRPS uniquement). Ils se pilotent en JavaScript
et mémorisent le refus dans le `localStorage`. Ne pas les dupliquer dans une page :
pour toute modification de leur comportement, voir la skill `pwa-django`.
