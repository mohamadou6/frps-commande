from pathlib import Path

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from fpdf import FPDF

_PDF_SIGNER = TimestampSigner(salt="commande-pdf")
_PDF_TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 jours

ASSETS_DIR = Path(__file__).resolve().parent / "pdf_assets"
LOGO_FRPS = ASSETS_DIR / "logo_frps.jpeg"
LOGO_CSU = ASSETS_DIR / "logo_csu.jpg"
LOGOS_PARTENAIRES = [
    ASSETS_DIR / "logo_cooperation_allemande.png",
    ASSETS_DIR / "logo_kfw.png",
    ASSETS_DIR / "logo_ministere_sante.png",
    ASSETS_DIR / "logo_banque_mondiale.jpeg",
    ASSETS_DIR / "logo_afd.jpeg",
    ASSETS_DIR / "logo_c2d.png",
]


def generer_token_pdf(commande_id) -> str:
    """Jeton signé permettant de récupérer le PDF sans authentification (utilisé par Twilio)."""
    return _PDF_SIGNER.sign(str(commande_id))


def verifier_token_pdf(commande_id, token: str) -> bool:
    try:
        valeur = _PDF_SIGNER.unsign(token, max_age=_PDF_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return valeur == str(commande_id)


class CommandePDF(FPDF):
    """En-tête (mention République/Région/FRPS + logo) et pied de page (logos des
    partenaires du programme) repris du modèle de lettre à en-tête officiel du GIP-FRPS
    Nord (fichier `NOTE SERVICE CSU INFOR ET GESTION DES DATA.docx`)."""

    def header(self):
        self.image(str(LOGO_CSU), x=10, y=6, w=30)
        self.image(str(LOGO_FRPS), x=self.w - 10 - 30, y=6, w=30)

        largeur_page = self.w - 20  # marges gauche/droite de 10mm

        def ligne_centree(texte, taille, gras=False):
            self.set_x(10)
            self.set_font("Helvetica", "B" if gras else "", taille)
            self.cell(largeur_page, 4, texte, align="C", new_x="LMARGIN", new_y="NEXT")

        self.set_y(8)
        ligne_centree("REPUBLIQUE DU CAMEROUN", 9, gras=True)
        ligne_centree("Paix - Travail - Patrie", 7)
        ligne_centree("REGION DU NORD", 8, gras=True)
        ligne_centree("FONDS REGIONAL POUR LA PROMOTION DE LA SANTE DU NORD", 8, gras=True)

        self.ln(2)
        ligne_centree("GIP - FRPS NORD", 11, gras=True)
        ligne_centree("GROUPEMENT D'INTERET PUBLIC", 8)

        self.ln(1)
        self.set_draw_color(0, 0, 0)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        y = self.h - 22
        largeur_logo = 15
        ecart = 6
        largeur_totale = len(LOGOS_PARTENAIRES) * largeur_logo + (len(LOGOS_PARTENAIRES) - 1) * ecart
        x = (self.w - largeur_totale) / 2
        for logo in LOGOS_PARTENAIRES:
            self.image(str(logo), x=x, y=y, w=largeur_logo)
            x += largeur_logo + ecart

        self.set_y(-6)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 4, f"Page {self.page_no()}/{{nb}}", align="C")


def generer_pdf_commande(commande) -> bytes:
    """Génère le PDF récapitulatif d'une commande validée (pour envoi WhatsApp)."""
    pdf = CommandePDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=28)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Bon de Commande FRPS #{commande.pk}", new_x="LMARGIN", new_y="NEXT")

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
    pdf.set_font("Helvetica", "", 10)
    # `table()` (et non `cell()`) pour que les noms de produits longs passent à la ligne
    # dans la colonne Produit au lieu de déborder sur la colonne Quantité.
    with pdf.table(
        width=185,  # même largeur totale que la ligne "Total" ci-dessous
        col_widths=(90, 25, 35, 35),
        align="LEFT",
        text_align=("LEFT", "CENTER", "RIGHT", "RIGHT"),
        line_height=6,
        padding=1,
        repeat_headings=1,  # ré-affiche l'en-tête si la table continue page suivante
    ) as table:
        entete = table.row()
        for titre in ("Produit", "Quantité", "Prix unit.", "Sous-total"):
            entete.cell(titre)
        for ligne in commande.lignes.select_related("produit"):
            rangee = table.row()
            rangee.cell(ligne.produit.nom)
            rangee.cell(str(ligne.quantite))
            rangee.cell(f"{ligne.prix_unitaire_snapshot} FCFA")
            rangee.cell(f"{ligne.sous_total} FCFA")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(150, 10, "Total", border=1, align="R")
    pdf.cell(35, 10, f"{commande.montant_total} FCFA", border=1, align="R")

    return bytes(pdf.output())
