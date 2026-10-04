from decimal import ROUND_HALF_UP, Decimal


def arrondir_montant(valeur) -> Decimal:
    """Total général ramené au FCFA entier, demi vers le haut (12,50 -> 13).

    Règle unique pour toute l'application, alignée sur `floatformat:"0"` des
    gabarits : `round()` de Python arrondit au pair (12,50 -> 12), ce qui faisait
    diverger d'un franc l'écran et le PDF d'une même commande."""
    return Decimal(str(valeur)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def formater_montant(valeur) -> str:
    """Total général : arrondi (sans décimales), séparateur de milliers. Pour un
    prix unitaire ou le total d'une ligne, voir formater_prix qui conserve les
    décimales."""
    return f"{int(arrondir_montant(valeur)):,}".replace(",", " ")


def formater_prix(valeur) -> str:
    """Prix unitaire ou total d'une ligne : décimales conservées, séparateur de
    milliers ajouté."""
    texte = f"{float(valeur):,.2f}"
    entier, _, decimales = texte.partition(".")
    signe = ""
    if entier.startswith("-"):
        signe, entier = "-", entier[1:]
    return f"{signe}{entier.replace(',', ' ')},{decimales}"
