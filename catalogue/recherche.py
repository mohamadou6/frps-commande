"""Recherche de produits, tolérante aux fautes de frappe.

**Ces règles existent en double** : ici (serveur) et dans accounts/static/js/app.js
(recherche instantanée du catalogue, sur le téléphone). Toute modification se fait
aux deux endroits ; les synonymes, eux, sont transmis au téléphone par la page
(`synonymes_json`), ils ne sont écrits qu'ici.

Règles :
- majuscules, accents, espaces et ponctuation ignorés ; « y » lu comme « i » ;
- lettres doublées fusionnées (« amoxiciline » trouve « amoxicilline ») ;
- chaque mot cherché doit se retrouver dans le nom ;
- un mot de 5 lettres ou plus tolère une faute (lettre en trop, en moins ou changée) ;
- un mot peut aussi être trouvé par un synonyme (molécule / nom courant).
"""

import json
import re
import unicodedata

# Synonymes, dans les deux sens. Clés et valeurs écrites simplement : elles sont
# normalisées au chargement. À compléter avec le FRPS au fil des recherches ratées.
_SYNONYMES = [
    ("paracetamol", "acetaminophene"),
    ("aspirine", "acetylsalicylique"),
    ("sro", "rehydratation"),
    ("vitamine", "vit"),
    ("antipaludeen", "artemether"),
    ("antipaludeen", "artesunate"),
    ("antipaludeen", "quinine"),
    ("antibiotique", "amoxicilline"),
    ("antibiotique", "ampicilline"),
    ("antibiotique", "ceftriaxone"),
    ("seringue", "aiguille"),
]

TOLERANCE_LONGUEUR_MIN = 5

_RE_MOTS = re.compile(r"[^\W_]+", re.UNICODE)
_RE_DOUBLES = re.compile(r"([^\W\d_])\1+", re.UNICODE)


def normaliser(texte):
    texte = unicodedata.normalize("NFD", str(texte or "").strip().lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c)).replace("y", "i")
    # Lettres doublées seulement : « 100 mg » ne doit pas devenir « 10 mg ».
    return _RE_DOUBLES.sub(r"\1", texte)


def mots(texte):
    return _RE_MOTS.findall(normaliser(texte))


def compact(texte):
    return "".join(mots(texte))


def _construire_synonymes():
    table = {}
    for a, b in _SYNONYMES:
        a, b = compact(a), compact(b)
        table.setdefault(a, set()).add(b)
        table.setdefault(b, set()).add(a)
    return {cle: sorted(valeurs) for cle, valeurs in table.items()}


SYNONYMES = _construire_synonymes()


def synonymes_json():
    """Pour le téléphone (attribut data de la page), afin d'appliquer la même règle."""
    return json.dumps(SYNONYMES, ensure_ascii=False)


def _au_plus_une_faute(a, b):
    """Vrai si a et b diffèrent d'au plus une lettre (ajout, retrait ou remplacement)."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = fautes = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        fautes += 1
        if fautes > 1:
            return False
        if len(a) == len(b):
            i += 1
        j += 1
    return fautes + (len(b) - j) + (len(a) - i) <= 1


def _mot_present(mot, nom_compact):
    if mot in nom_compact:
        return True
    if len(mot) < TOLERANCE_LONGUEUR_MIN:
        return False
    n = len(mot)
    for debut in range(len(nom_compact) - n + 2):
        for longueur in (n - 1, n, n + 1):
            morceau = nom_compact[debut:debut + longueur]
            if len(morceau) == longueur and _au_plus_une_faute(mot, morceau):
                return True
    return False


def correspond(mot, nom_compact):
    if _mot_present(mot, nom_compact):
        return True
    return any(synonyme in nom_compact for synonyme in SYNONYMES.get(mot, ()))


def filtrer(produits, requete):
    """Produits (liste ou queryset) dont le nom contient tous les mots de `requete`,
    selon les règles du module. L'ordre est conservé. Requête vide : tout passe."""
    cherches = mots(requete)
    if not cherches:
        return list(produits)
    return [p for p in produits if all(correspond(mot, compact(p.nom)) for mot in cherches)]
