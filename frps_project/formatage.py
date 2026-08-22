def formater_montant(valeur) -> str:
    """Montant arrondi (sans décimales), séparateur de milliers. Pour un prix
    unitaire, voir formater_prix qui conserve les décimales."""
    return f"{int(round(valeur)):,}".replace(",", " ")


def formater_prix(valeur) -> str:
    """Prix unitaire : décimales conservées, séparateur de milliers ajouté."""
    texte = f"{float(valeur):,.2f}"
    entier, _, decimales = texte.partition(".")
    signe = ""
    if entier.startswith("-"):
        signe, entier = "-", entier[1:]
    return f"{signe}{entier.replace(',', ' ')},{decimales}"
