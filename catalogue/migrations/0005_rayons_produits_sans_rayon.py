"""Rattache à un rayon les produits en stock qui n'en avaient pas.

Source : classement fait par le FRPS dans « produits_sans_rayon_MP_SR_KAN_2026-10-19.xlsx »
(Magasin Principal et Magasin SR ; rien pour le Magasin KAN), avec trois corrections
validées par le FRPS : Phénobarbital ampoule en Injectables, Bétadine et Benzoate de
benzyle en Application externe. Crée au passage le rayon
« Application externe » (crèmes, pommades, aérosols).

Seuls les produits encore sans rayon sont touchés : un classement déjà corrigé à la main
dans l'admin n'est jamais écrasé.
"""

from django.db import migrations

NOUVEAU_RAYON = ("application-externe", "Application externe", "🖐️", 9)

CLASSEMENT = {
    "injectables": [
        "ACID_TRAN_1G_INJ//", "ARTESU_60//_AM-IV", "BENZYLP_1MEGA", "PHENOB_100/_AM_IV",
        "BUPIVA_0.5%_SI_IV", "CEFOTA_1000_SI_IV", "CEFUROX_750MG_INJ/", "CHLORAM_1G",
        "CIPRO_200///", "ENOXA_4000_UI///", "EPHED_50MG///", "FENTA_50MG///",
        "LEVOFLOX_500MG////", "LIDADR_2%50_SI_IV", "MORPCH_10//_AM_IV", "NICARD_INJ///",
        "OFLOXA_200/_SI_IV", "RANITI_25//_SI_IV", "SALBUT_500B_AM_IV",
        "TRAMA_INJ_100MG///", "VERCURO_4MG///", "VIT_C_INJ///", "ACITRANS",
    ],
    "comprimes": [
        "ACECLO_PAR_600MG//", "ALBEND_400/_CP_OR", "ALUIN_MAGNES_500//", "AMITRIP_25G/////",
        "CAPTO_25MG", "CARBA_200MG", "CEFIXI_200M_CP_OR", "CELECOX_200MG", "FERCOM_////_CP_OR",
        "FUROSE_40//_CP_OR", "GLIBEN_5///_CP_OR", "GRISEO_500/_CP_OR", "LOPECH_2///_CP_OR",
        "MEBEND_100/_CP_OR", "METFOR_500/_CP_OR", "VITAMM_////_CP_OR", "NIFEDI_10//_CP_OR",
        "OFLOXA_200/_CP_OR", "PHENOB_100/_CP_OR", "PREDNI_5///_CP_OR", "RANITI_150/_CP_OR",
        "SALBUT_2///_CP_OR", "VITAMINE_C_500MG//",
    ],
    "sirops": [
        "ARTLUM_1260_SP_OR", "AZYTHRO", "CEFIXI_100/_SP_OR", "ERYTHR_25//_SP_OR",
        "FLUCLOX_100ML///", "FLUCONA_200MG////", "CHLORPARPHENYL",
    ],
    "application-externe": [
        "DICLO_30G///", "KETONAZ_2%_30G////", "MICONA_2%//_CR_30", "NEOBAC_0.5%_PM_CU",
        "SALBAE_200/_CL_OR", "POLYVI_4%_1000M///", "BENZOA_25%/_SC_12",
    ],
}


def classer(apps, schema_editor):
    Rayon = apps.get_model("catalogue", "Rayon")
    Produit = apps.get_model("catalogue", "Produit")

    slug, nom, icone, ordre = NOUVEAU_RAYON
    Rayon.objects.get_or_create(slug=slug, defaults={"nom": nom, "icone": icone, "ordre": ordre})

    for slug_rayon, codes in CLASSEMENT.items():
        rayon = Rayon.objects.filter(slug=slug_rayon).first()
        if rayon is None:
            continue
        Produit.objects.filter(code_sage__in=codes, rayon__isnull=True).update(rayon=rayon)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0004_import_rayons_data"),
    ]

    operations = [
        migrations.RunPython(classer, migrations.RunPython.noop),
    ]
