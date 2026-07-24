from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from fpdf import FPDF

_PDF_SIGNER = TimestampSigner(salt="commande-pdf")
_PDF_TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 jours


def generer_token_pdf(commande_id) -> str:
    """Jeton signé permettant de récupérer le PDF sans authentification (utilisé par Twilio)."""
    return _PDF_SIGNER.sign(str(commande_id))


def verifier_token_pdf(commande_id, token: str) -> bool:
    try:
        valeur = _PDF_SIGNER.unsign(token, max_age=_PDF_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return valeur == str(commande_id)


def generer_pdf_commande(commande) -> bytes:
    """Génère le PDF récapitulatif d'une commande validée (pour envoi WhatsApp)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Commande FRPS #{commande.pk}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 11)
    formation = commande.formation_sanitaire
    pdf.cell(0, 8, f"Formation sanitaire : {formation.nom}", new_x="LMARGIN", new_y="NEXT")
    if formation.region:
        pdf.cell(0, 8, f"Région / District : {formation.region} / {formation.district}", new_x="LMARGIN", new_y="NEXT")
    if commande.date_confirmation:
        pdf.cell(
            0, 8, f"Date de confirmation : {commande.date_confirmation:%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT"
        )

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(90, 8, "Produit", border=1)
    pdf.cell(25, 8, "Quantité", border=1, align="C")
    pdf.cell(35, 8, "Prix unit.", border=1, align="R")
    pdf.cell(35, 8, "Sous-total", border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    for ligne in commande.lignes.select_related("produit"):
        pdf.cell(90, 8, ligne.produit.nom, border=1)
        pdf.cell(25, 8, str(ligne.quantite), border=1, align="C")
        pdf.cell(35, 8, f"{ligne.prix_unitaire_snapshot} FCFA", border=1, align="R")
        pdf.cell(35, 8, f"{ligne.sous_total} FCFA", border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(150, 10, "Total", border=1, align="R")
    pdf.cell(35, 10, f"{commande.montant_total} FCFA", border=1, align="R")

    return bytes(pdf.output())
