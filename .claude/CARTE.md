# Carte du code — commande-frps

<!-- Genere par la skill carte-du-code le 2026-11-18. NE PAS EDITER A LA MAIN : relancer scripts/generer_carte.py. -->

**Lire ce fichier avant d'explorer le depot.** Il donne `fichier:ligne` pour chaque modele, URL, vue et fonction.

10 modules · 19 modeles · 64 URLs · 173 fonctions · 35 gabarits · 9463 lignes de Python

## accounts (514 lignes)

### `accounts/admin.py` (43 l.)
- *admin* **FormationSanitaireAdmin** :38
- *classe* **UserAdmin**(BaseUserAdmin) :8 — Utilisé par un admin FRPS pour créer les comptes (formations sanitaires et personnel).
  - methodes : save_model() :23

### `accounts/decorators.py` (114 l.)
- `_deconnecter_fosa_sans_fiche(request)` :13 — Session ouverte par un compte FOSA sans fiche (avant que la connexion ne le
- `formation_sanitaire_required(view_func)` :23 — Réservé aux formations sanitaires. L'admin FRPS a accès à tout (y compris
- `personnel_frps_required(view_func)` :41
- `admin_frps_required(view_func)` :52 — Réservé au compte super admin FRPS (role=admin). Utilisé pour les actions
- `comptabilite_frps_required(view_func)` :66 — Réservé au personnel comptabilité et à l'admin FRPS. Utilisé pour la mise à
- `stock_frps_required(view_func)` :81 — Réservé au personnel stock et à l'admin FRPS : avancer une commande dans sa
- `formation_sanitaire_only_required(view_func)` :95 — Réservé aux comptes ayant un vrai profil FormationSanitaire (panier, commandes,

### `accounts/forms.py` (23 l.)
- *classe* **ConnexionForm**(AuthenticationForm) :10 — Refuse la connexion d'un compte FOSA sans fiche FormationSanitaire : connecté,
  - methodes : confirm_login_allowed() :18
- *const* `MESSAGE_FOSA_SANS_FICHE = "Ce compte n'est rattaché à aucune forma` :4

### `accounts/management/commands/ensure_admin.py` (32 l.)
- *classe* **Command**(BaseCommand) :7 — Crée le compte admin FRPS s'il n'existe pas encore, à partir des variables
  - methodes : handle() :16

### `accounts/management/commands/import_fosa.py` (71 l.)
- *classe* **Command**(BaseCommand) :13 — Importe le référentiel des formations sanitaires (région/district/nom) depuis
  - methodes : handle() :25, _username_unique() :63

### `accounts/management/commands/seed_demo.py` (36 l.)
- *classe* **Command**(BaseCommand) :6
  - methodes : handle() :9

### `accounts/models.py` (79 l.)
- *enum* **Role** :6 — ADMIN, FORMATION_SANITAIRE, PERSONNEL_STOCK, PERSONNEL_COMPTABILITE
- *modele* **User** :17
  - champs : role(Char choices=Role.choices), telephone(Char)
  - methodes : is_formation_sanitaire() :26, fiche_fosa() :30, est_fosa_sans_fiche() :43, is_admin_frps() :47, is_personnel_stock() :51, is_personnel_comptabilite() :55
- *modele* **FormationSanitaire** :62
  - champs : user(OneToOne ->User related_name=formation_sanitaire), nom(Char), region(Char), district(Char), adresse(Char), telephone_contact(Char), actif(Boolean), date_creation(DateTime)

### `accounts/tests.py` (90 l.)
- *classe* **CompteFosaSansFicheTests**(TestCase) :11 — Un compte au rôle FOSA sans fiche FormationSanitaire faisait tomber toutes les
  - tests : test_connexion_refusee_avec_le_motif, test_mauvais_mot_de_passe_garde_le_message_habituel, test_session_deja_ouverte_les_pages_communes_ne_plantent_plus, test_session_deja_ouverte_deconnectee_avec_le_motif, test_compte_fosa_avec_fiche_se_connecte
- *classe* **AdminCreationCompteTests**(TestCase) :60
  - tests : test_compte_fosa_sans_fiche_signale, test_compte_personnel_pas_d_avertissement
- *const* `MOT_DE_PASSE = 'Tres-Secret-987'` :8

### `accounts/views.py` (26 l.)
- *classe* **LoginView**(LoginView) :10 — Redirige après connexion selon le rôle : catalogue pour les formations
  - methodes : get_success_url() :22

## catalogue (1587 lignes)

### `catalogue/admin.py` (41 l.)
- *admin* **RayonAdmin** :8 — list_editable=ordre
- *admin* **ProduitAdmin** :15 — list_editable=prix_unitaire, stock_disponible, magasin, rayon, actif
- *admin* **BaissePrixAdmin** :32 — list_editable=visible

### `catalogue/context_processors.py` (11 l.)
- `offres(request)` :4 — Nombre de promotions (offres spéciales + prix en baisse), pour la pastille du menu des FOSA. `fiche_fosa`

### `catalogue/management/commands/import_catalogue.py` (70 l.)
- *classe* **Command**(BaseCommand) :21 — Importe/actualise le catalogue depuis catalogue/data/produits_magasin_principal.csv
  - methodes : handle() :29

### `catalogue/management/commands/import_rayons.py` (63 l.)
- *classe* **Command**(BaseCommand) :23 — Crée/actualise les rayons puis rattache les produits selon
  - methodes : handle() :31

### `catalogue/management/commands/update_stock.py` (137 l.)
- *classe* **Command**(BaseCommand) :72 — Met à jour prix_unitaire/stock_disponible depuis un fichier CSV fourni par
  - methodes : add_arguments() :86, handle() :90
- `_read_updates_with_code_sage(path)` :23 — Fichier avec code_sage (colonnes code_sage;nom;...;prix_unitaire;stock_disponible,
- `_read_updates_by_position(update_csv)` :45 — Fichier sans code_sage (colonnes nom;prix_unitaire;stock_disponible). Le nom seul

### `catalogue/models.py` (146 l.)
- *enum* **Magasin** :11 — PRINCIPAL, UCPC, AUTRE
- *modele* **Rayon** :17 — Rayon de classification du catalogue (ex. Injectables, Comprimés).
  - champs : slug(Slug), nom(Char), icone(Char), ordre(PositiveSmallInteger)
- *modele* **Produit** :37 — Catalogue saisi et maintenu manuellement par l'admin FRPS via l'admin Django
  - champs : code_sage(Char), nom(Char), unite(Char), prix_unitaire(Decimal), stock_disponible(PositiveInteger), magasin(Char choices=Magasin.choices), actif(Boolean), derniere_synchro(DateTime), rayon(ForeignKey ->Rayon related_name=produits)
  - methodes : en_stock() :69, niveau_stock() :73
- *modele* **BaissePrix** :93 — Trace d'une baisse du prix de vente, enregistrée à l'import Excel, dans l'admin
  - champs : produit(ForeignKey ->Produit related_name=baisses_prix), ancien_prix(Decimal), nouveau_prix(Decimal), date(DateTime), visible(Boolean)
- *modele* **Promotion** :115 — Prix promotionnel décidé par l'admin FRPS pour une période. Pendant la période,
  - champs : produit(ForeignKey ->Produit related_name=promotions), prix_promotionnel(Decimal), date_debut(Date), date_fin(Date), message(Char), active(Boolean), creee_par(ForeignKey ->accounts.User related_name=+), date_creation(DateTime)
  - methodes : pourcentage() :142
- *const* `SEUIL_STOCK_CRITIQUE = 10` :7
- *const* `SEUIL_STOCK_FAIBLE = 50` :8
- *const* `PROMOTION_DUREE_JOURS = 30` :89
- *const* `PROMOTION_SEUIL_POURCENT = 1` :90

### `catalogue/services.py` (206 l.)
- `_promotions_du_jour()` :35 — Promotions actives aujourd'hui dont le prix est encore sous le prix normal (si
- `promotions_en_cours()` :48 — Promotions visibles des FOSA : en cours et sur un produit commandable.
- `prix_promotionnels(produit_ids)` :58 — {produit_id: prix promotionnel} des promotions du jour. Une seule requête pour
- `prix_de_vente(produit, promos)` :70 — Prix que la FOSA paie aujourd'hui : le prix promotionnel s'il y en a un, sinon
- `creer_promotion(produit, prix_promotionnel, date_debut, date_fin, message, auteur)` :79
- `arreter_promotion(promotion)` :119
- `noter_baisses_prix(changements)` :128 — Enregistre les baisses de prix parmi `changements` : [(produit, ancien_prix, nouveau_prix)].
- `baisses_prix_recentes()` :144 — Produits dont le prix de vente a baissé récemment : une entrée par produit, la
- `masquer_baisse(produit)` :183 — Retire un produit du menu Baisses de prix (toutes ses baisses de la période).
- `toutes_les_promotions()` :189 — Les deux types de promotion présentés aux FOSA dans le menu Promotions :
- `nombre_promotions()` :201 — Total des deux types, pour la pastille du menu et le bandeau du catalogue.

### `catalogue/tests.py` (198 l.)
- *classe* **ImportVariationDePrixTests**(TestCase) :28 — L'import signale en couleur chaque prix qui monte ou qui baisse.
  - tests : test_chaque_ligne_porte_le_sens_de_variation_du_prix, test_les_changements_de_prix_passent_en_tete, test_la_page_colore_hausse_et_baisse
- *classe* **MigrationRayonsProduitsSansRayonTests**(TestCase) :60
  - tests : test_range_les_produits_sans_rayon_et_cree_application_externe, test_n_ecrase_pas_un_rayon_deja_choisi_a_la_main, test_phenobarbital_betadine_et_benzoate_finissent_en_injectables, test_le_classement_couvre_les_60_produits_du_fichier_sans_doublon
- *classe* **RayonAutresTests**(TestCase) :102 — Les produits sans rayon sont regroupés dans un rayon « Autres » du catalogue.
  - tests : test_autres_apparait_en_fin_de_liste_avec_les_produits_disponibles_sans_rayon, test_filtrer_sur_autres_ne_montre_que_les_produits_sans_rayon, test_pas_de_rayon_autres_quand_tout_est_range
- *classe* **MigrationRayonsLaboratoireMaterielTests**(TestCase) :135
  - tests : test_cree_les_deux_rayons_et_range_selon_le_fichier, test_n_ecrase_pas_un_rayon_existant, test_le_fichier_ne_cite_que_des_rayons_connus_sans_doublon
- *classe* **MigrationRayonsQuatreDerniersProduitsTests**(TestCase) :171 — Les 4 produits absents du fichier du 25/10/2026 : plus aucun produit sans rayon.
  - tests : test_range_les_quatre_produits_dans_le_rayon_prevu, test_n_ecrase_pas_un_rayon_deja_choisi_a_la_main, test_ne_cite_que_des_rayons_existants

### `catalogue/tests_import.py` (84 l.)
- *classe* **ImportProduitsTests**(TestCase) :25 — Import Excel des prix et du stock par l'admin FRPS : la seule façon de mettre
  - tests : test_met_a_jour_prix_et_stock, test_colonnes_dans_un_autre_ordre_et_intitules_proches, test_cree_un_produit_inconnu_avec_son_nom, test_lignes_vides_et_codes_vides_ignores, test_colonne_manquante_ne_change_rien, test_un_fichier_qui_n_est_pas_excel_est_refuse, test_reserve_a_l_admin

### `catalogue/tests_promotions.py` (226 l.)
- *classe* **PromotionTests**(TestCase) :35
  - tests : test_le_prix_promotionnel_est_paye_pendant_la_promotion, test_prix_normal_avant_et_apres_la_periode, test_le_dernier_jour_est_inclus, test_promotion_arretee_rend_le_prix_normal, test_commande_hors_connexion_au_prix_promotionnel, test_si_le_prix_normal_passe_sous_la_promo_le_plus_bas_s_applique, test_prix_superieur_ou_egal_au_prix_normal_refuse, test_periode_passee_ou_inversee_refusee, test_deux_promotions_qui_se_chevauchent_refusees, test_la_fosa_voit_la_promotion_et_le_bandeau_du_catalogue, test_produit_en_rupture_absent_des_promotions, test_l_admin_cree_et_arrete_une_promotion_depuis_l_application, test_gestion_reservee_a_l_admin, test_compteur_du_menu
- *classe* **BaissePrixTests**(TestCase) :152 — Baisses durables du prix de vente : détectées seules, signalées à part des promotions.
  - tests : test_import_excel_enregistre_les_baisses_seulement, test_baisse_infime_ignoree, test_baisse_dans_l_admin_django_enregistree, test_la_baisse_est_un_type_de_promotion, test_produit_en_offre_speciale_pas_repete_dans_les_baisses, test_compteur_du_menu_compte_les_deux_types, test_prix_remonte_plus_signale, test_baisse_ancienne_plus_signalee, test_l_admin_masque_une_baisse

### `catalogue/urls.py` (15 l.)
- URL `''` -> views.liste  `catalogue:liste` :8
- URL `importer/` -> views.importer_produits  `catalogue:importer` :9
- URL `promotions/` -> views.promotions  `catalogue:promotions` :10
- URL `promotions/gerer/` -> views.gerer_promotions  `catalogue:gerer_promotions` :11
- URL `promotions/<int:promotion_id>/arreter/` -> views.arreter_promotion  `catalogue:arreter_promotion` :12
- URL `promotions/baisse/<int:produit_id>/masquer/` -> views.masquer_baisse  `catalogue:masquer_baisse` :13

### `catalogue/views.py` (390 l.)
- `liste(request)` :24 @formation_sanitaire_required
- `_quantites_panier(request)` :86 — Quantités déjà au panier de la FOSA ({produit_id: quantité}). L'admin FRPS n'a
- `_annoter_offres(produits, quantites_panier)` :97 — Pose sur chaque fiche : quantité au panier, prix du jour (promotion comprise)
- `promotions(request)` :113 @formation_sanitaire_required — Menu Promotions des FOSA, deux types :
- `masquer_baisse(request, produit_id)` :145 @admin_frps_required @require_POST
- `gerer_promotions(request)` :153 @admin_frps_required — Mettre un produit en promotion (prix promotionnel + période) et suivre les
- `arreter_promotion(request, promotion_id)` :207 @admin_frps_required @require_POST
- `_lire_fichier_produits(fichier)` :230 — Lit un classeur Excel dont l'en-tête contient une colonne code produit
- `importer_produits(request)` :286 @admin_frps_required
- *const* `SLUG_AUTRES = 'autres'` :20

## commandes (2074 lignes)

### `commandes/admin.py` (21 l.)
- *admin* **LigneCommandeInline** :6
- *admin* **CommandeAdmin** :14

### `commandes/context_processors.py` (22 l.)
- `panier_resume(request)` :4 — Nombre de lignes du panier en cours, pour le badge de la navbar : sans lui,

### `commandes/models.py` (174 l.)
- *enum* **StatutCommande** :9 — BROUILLON, CONFIRMEE, PAYEE, ANNULEE, EN_ATTENTE_SYNCHRO
- *enum* **EtapeTraitement** :21 — RECUE, EN_PREPARATION, PRETE, LIVREE
- *modele* **Commande** :37
  - champs : formation_sanitaire(ForeignKey ->accounts.FormationSanitaire related_name=commandes), statut(Char choices=StatutCommande.choices), montant_total(Decimal), date_creation(DateTime), date_confirmation(DateTime), uuid_client(UUID), etape(Char choices=EtapeTraitement.choices), date_preparation(DateTime), date_prete(DateTime), date_livraison(DateTime)
  - methodes : recalculer_montant() :64, preparee_hors_ligne() :75, est_effective() :79, etape_suivante() :84, etape_suivante_libelle() :92, etapes_suivi() :97, montant_paye() :112, solde_restant() :117, etat_paiement() :125
- *modele* **LigneCommande** :142
  - champs : commande(ForeignKey ->Commande related_name=lignes), produit(ForeignKey ->catalogue.Produit related_name=lignes_commande), quantite(PositiveInteger), prix_unitaire_snapshot(Decimal), quantite_demandee(PositiveInteger)
  - methodes : servie_en_partie() :165, sous_total() :170
- *classe* **LigneCommandeQuerySet**(QuerySet) :134
  - methodes : servies() :135

### `commandes/recherche.py` (106 l.)
- `filtrer_commandes(commandes, params)` :37 — Applique les critères de recherche à `commandes`.
- `resume(commandes)` :102 — Nombre de commandes trouvées et montant total de celles qui ont été validées.

### `commandes/services.py` (363 l.)
- *classe* **StockInsuffisantError**(Exception) :15
- *classe* **DemandeInvalideError**(ValueError) :19 — Demande hors connexion que le serveur ne peut pas accepter, même en la renvoyant.
- `get_panier(formation_sanitaire)` :23 — Retourne le panier (commande brouillon) en cours, en crée un si besoin.
- `ajouter_produit(commande, produit, quantite)` :33
- `retirer_produit(commande, produit)` :57
- `confirmer_commande(commande)` :62 — Verrouille la commande, débite le stock, notifie le personnel FRPS chargé du stock.
- `_debiter_stock(lignes)` :82 — À appeler dans une transaction : une ligne refusée lève StockInsuffisantError,
- `synchroniser_demande(formation_sanitaire, uuid_client, quantites, panier_id)` :107 — Reçoit puis valide une demande hors connexion. Retourne (commande, reçue_maintenant).
- `recevoir_demande(formation_sanitaire, uuid_client, quantites, panier_id)` :119 — Enregistre la demande telle qu'envoyée, sans toucher au stock.
- `valider_demande(commande)` :194 — Sert la demande avec le stock et les prix du moment, puis la confirme.
- `supprimer_commande(commande)` :250 — Supprime une commande et remet en stock ce qu'elle avait débité.
- `avancer_etape(commande, etape_attendue)` :296 — Fait passer la commande à l'étape suivante et prévient la FOSA quand elle est prête.
- `recommander(commande, formation_sanitaire)` :330 — Remet dans le panier les produits d'une commande passée.

### `commandes/tests.py` (643 l.)
- *classe* **CommandeWorkflowTests**(TestCase) :23
  - tests : test_ajouter_produit_respecte_le_stock, test_confirmer_commande_notifie_personnel_stock, test_confirmer_panier_vide_leve_une_erreur
- *classe* **TelechargerPdfTests**(TestCase) :59
  - tests : test_le_proprietaire_peut_telecharger_le_pdf, test_un_autre_utilisateur_ne_peut_pas_telecharger
- *classe* **SupprimerCommandeTests**(TestCase) :90 — Suppression d'une commande validée par erreur par une FOSA, réservée à l'admin.
  - tests : test_supprimer_une_commande_confirmee_remet_le_stock, test_supprimer_un_brouillon_ne_gonfle_pas_le_stock, test_admin_peut_supprimer_via_le_bouton, test_personnel_non_admin_ne_peut_pas_supprimer, test_fosa_ne_peut_pas_supprimer_sa_propre_commande, test_un_simple_GET_ne_supprime_rien, test_le_bouton_n_apparait_que_pour_l_admin
- *classe* **ArrondiDesMontantsTests**(TestCase) :184 — Le prix unitaire et le total de chaque ligne gardent leurs décimales ; seul le
  - tests : test_le_total_general_est_arrondi_les_lignes_gardent_leurs_decimales, test_un_total_en_virgule_cinquante_monte_au_franc_superieur, test_la_page_affiche_la_ligne_avec_decimales_et_le_total_arrondi, test_la_migration_arrondit_les_commandes_deja_passees
- *classe* **AjoutAuPanierSansRechargementTests**(TestCase) :248 — Le catalogue ajoute au panier sans recharger la page (js/app.js) : sur le réseau
  - tests : test_ajout_instantane_repond_en_json_avec_le_panier_a_jour, test_stock_insuffisant_renvoie_le_message_sans_rien_ajouter, test_quantite_illisible_donne_un_message_en_francais, test_sans_javascript_le_formulaire_ramene_au_catalogue, test_le_catalogue_active_lajout_instantane_pour_la_fosa, test_les_fiches_portent_le_produit_pour_l_ajout_sans_reseau
- *classe* **CommandeHorsConnexionTests**(TestCase) :313 — Commande préparée sans réseau sur le téléphone (js/demandes.js), envoyée au retour
  - tests : test_la_demande_est_validee_a_son_arrivee, test_un_renvoi_de_la_meme_demande_ne_cree_ni_doublon_ni_second_debit, test_stock_insuffisant_a_l_arrivee_sert_ce_qui_reste, test_rien_de_disponible_annule_la_demande_sans_debit_ni_notification, test_le_prix_est_recalcule_au_serveur, test_un_produit_desactive_entre_temps_n_est_pas_servi, test_un_produit_supprime_du_catalogue_est_ignore, test_le_meme_produit_en_double_est_additionne, test_une_demande_restee_en_attente_est_terminee_au_renvoi, test_une_demande_en_attente_ne_compte_pas_comme_commande_effective, test_l_identifiant_d_une_autre_fosa_est_refuse_sans_rien_reveler, test_une_demande_preparee_sous_un_autre_compte_n_est_pas_traitee, test_une_demande_illisible_est_refusee_sans_rien_creer, test_un_simple_GET_ne_cree_rien, test_le_personnel_frps_ne_peut_pas_envoyer_de_demande, test_sans_session_la_demande_n_est_pas_traitee, test_le_detail_montre_le_demande_et_le_servi, test_l_historique_signale_la_commande_preparee_hors_connexion, test_les_lignes_non_servies_restent_hors_du_sms_et_de_l_email, test_un_panier_confirme_sans_reseau_quitte_le_panier, test_une_ligne_changee_en_ligne_depuis_la_page_enregistree_reste_au_panier, test_le_panier_d_une_autre_fosa_n_est_pas_touche, test_un_renvoi_ne_retire_rien_de_plus_du_panier, test_la_page_du_panier_porte_de_quoi_le_confirmer_sans_reseau, test_une_commande_en_ligne_garde_son_affichage

### `commandes/tests_recherche.py` (99 l.)
- *classe* **RechercheHistoriqueTests**(TestCase) :17 — Recherche dans « Mes commandes » : par numéro, période, montant, produit, étape,
  - tests : test_sans_critere_toutes_mes_commandes_les_recentes_d_abord, test_jamais_les_commandes_d_une_autre_fosa, test_par_numero_avec_ou_sans_diese, test_par_periode, test_par_montant_avec_espaces, test_par_produit_servi_seulement, test_par_etape, test_par_paiement, test_tri_par_montant, test_resume_nombre_et_total, test_critere_illisible_signale_sans_vider_la_liste, test_aucun_resultat_message_adapte, test_pagination_garde_les_criteres

### `commandes/tests_suivi.py` (221 l.)
- *classe* **SuiviCommandeTests**(TestCase) :28 — Le personnel stock fait avancer une commande validée : reçue → en préparation →
  - tests : test_une_commande_validee_commence_a_l_etape_recue, test_les_etapes_s_enchainent_et_sont_datees, test_un_double_clic_ne_saute_pas_d_etape, test_la_fosa_recoit_un_sms_quand_la_commande_est_prete, test_sans_numero_l_etape_avance_quand_meme, test_la_comptabilite_consulte_sans_pouvoir_avancer, test_une_fosa_n_accede_pas_au_suivi, test_un_brouillon_ne_peut_pas_avancer, test_la_liste_de_travail_cache_les_commandes_livrees, test_le_compteur_nouvelles_suit_la_commande_d_etape_en_etape, test_retour_vers_une_adresse_externe_refuse, test_la_fosa_voit_l_etape_sur_sa_commande, test_la_migration_classe_les_anciennes_commandes_livrees
- *classe* **NumeroInternationalTests**(TestCase) :149
  - tests : test_formats_saisis_a_la_main
- *classe* **RecommanderTests**(TestCase) :158
  - tests : test_remet_les_produits_au_panier_sans_valider, test_plafonne_au_stock_et_ignore_l_indisponible, test_s_ajoute_a_ce_qui_est_deja_au_panier, test_reprend_la_quantite_demandee_hors_connexion, test_rien_de_disponible_ne_mene_pas_au_panier, test_une_autre_fosa_ne_peut_pas_recommander_ma_commande, test_un_simple_get_ne_fait_rien

### `commandes/urls.py` (24 l.)
- URL `''` -> views.panier  `commandes:panier` :8
- URL `ajouter/<int:produit_id>/` -> views.ajouter  `commandes:ajouter` :9
- URL `modifier-quantite/<int:produit_id>/` -> views.modifier_quantite  `commandes:modifier_quantite` :10
- URL `retirer/<int:produit_id>/` -> views.retirer  `commandes:retirer` :11
- URL `confirmer/` -> views.confirmer  `commandes:confirmer` :12
- URL `demandes/synchroniser/` -> views.synchroniser_demande  `commandes:synchroniser_demande` :13
- URL `historique/` -> views.historique  `commandes:historique` :14
- URL `suivi/` -> views.suivi  `commandes:suivi` :15
- URL `<int:commande_id>/etape/` -> views.avancer_etape  `commandes:avancer_etape` :16
- URL `<int:commande_id>/recommander/` -> views.recommander  `commandes:recommander` :17
- URL `<int:commande_id>/pdf/<str:token>/` -> views.pdf_commande  `commandes:pdf` :18
- URL `<int:commande_id>/telecharger/` -> views.telecharger_pdf  `commandes:telecharger_pdf` :19
- URL `<int:commande_id>/telecharger-staff/` -> views.telecharger_pdf_staff  `commandes:telecharger_pdf_staff` :20
- URL `<int:commande_id>/supprimer/` -> views.supprimer  `commandes:supprimer` :21
- URL `<int:commande_id>/` -> views.detail  `commandes:detail` :22

### `commandes/views.py` (401 l.)
- `panier(request)` :26 @formation_sanitaire_only_required
- `ajouter(request, produit_id)` :33 @formation_sanitaire_only_required @require_POST
- `modifier_quantite(request, produit_id)` :73 @formation_sanitaire_only_required @require_POST — Corrige la quantité d'une ligne directement depuis le panier : il fallait
- `retirer(request, produit_id)` :104 @formation_sanitaire_only_required @require_POST
- `confirmer(request)` :114 @formation_sanitaire_only_required @require_POST
- `_lire_quantites(lignes)` :133 — [{"produit": id, "quantite": n}, …] -> {id: n}. Lève ValueError si illisible.
- `synchroniser_demande(request)` :176 @formation_sanitaire_only_required @require_POST — Reçoit une commande préparée hors connexion (js/demandes.js) et la valide.
- `historique(request)` :216 @formation_sanitaire_only_required
- `detail(request, commande_id)` :247 @formation_sanitaire_only_required
- `telecharger_pdf(request, commande_id)` :257 @formation_sanitaire_only_required — Téléchargement du PDF par la FOSA elle-même (pour l'enregistrer ou le partager,
- `telecharger_pdf_staff(request, commande_id)` :270 @personnel_frps_required — Téléchargement du PDF par le personnel FRPS (depuis la page notifications),
- `pdf_commande(request, commande_id, token)` :280 — Sert le PDF de la commande sans authentification : accès protégé par un jeton
- `supprimer(request, commande_id)` :294 @admin_frps_required @require_POST — Suppression d'une commande par l'admin FRPS, avec remise en stock.
- `recommander(request, commande_id)` :310 @formation_sanitaire_only_required @require_POST
- `suivi(request)` :340 @personnel_frps_required — Commandes validées et leur étape de préparation. Par défaut, celles qui ne sont
- `avancer_etape(request, commande_id)` :386 @stock_frps_required @require_POST
- *const* `MAX_LIGNES_DEMANDE = 2000` :129
- *const* `MAX_QUANTITE_DEMANDEE = 10000000` :130

## frps_project (469 lignes)

### `frps_project/formatage.py` (29 l.)
- `arrondir_montant(valeur)` :4 — Total général ramené au FCFA entier, demi vers le haut (12,50 -> 13).
- `formater_montant(valeur)` :13 — Total général : arrondi (sans décimales), séparateur de milliers. Pour un
- `formater_prix(valeur)` :20 — Prix unitaire ou total d'une ligne : décimales conservées, séparateur de

### `frps_project/pwa.py` (81 l.)
- `service_worker(request)` :29 @require_GET @cache_control — `no-cache` : le navigateur doit revalider le fichier pour voir les mises à jour.
- `manifeste(request)` :41 @require_GET
- `assetlinks(request)` :46 @require_GET — Lien vérifié entre le domaine et l'application Android (Digital Asset Links).
- `hors_ligne(request)` :73 @require_GET — Page de repli affichée quand une page non encore consultée est demandée sans réseau.

### `frps_project/settings.py` (252 l.)
- *const* `AUTH_USER_MODEL = 'accounts.User'` :52
- *const* `ROOT_URLCONF = 'frps_project.urls'` :65
- *const* `WSGI_APPLICATION = 'frps_project.wsgi.application'` :86
- *const* `LANGUAGE_CODE = 'fr-fr'` :121
- *const* `TIME_ZONE = 'Africa/Douala'` :123
- *const* `USE_I18N = True` :125
- *const* `USE_THOUSAND_SEPARATOR = True` :129
- *const* `USE_TZ = True` :131
- *const* `STATIC_URL = 'static/'` :137
- *const* `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'` :145
- *const* `LOGIN_URL = 'login'` :147
- *const* `LOGIN_REDIRECT_URL = 'catalogue:liste'` :148
- *const* `LOGOUT_REDIRECT_URL = 'login'` :149

### `frps_project/tests_pwa.py` (78 l.)
- *classe* **HorsConnexionTests**(TestCase) :8 — Comportement sans réseau : servi par le service worker, vérifié ici sur le
  - tests : test_louverture_hors_ligne_retombe_sur_la_page_daccueil_du_compte, test_une_page_resservie_depuis_le_cache_est_marquee, test_la_page_pas_de_connexion_liste_les_pages_enregistrees, test_les_pages_portent_le_bandeau_hors_connexion
- *classe* **CommandeHorsConnexionPwaTests**(TestCase) :42 — Commande préparée sans réseau : envoyée par le service worker (Background Sync)
  - tests : test_le_service_worker_envoie_les_demandes_en_arriere_plan, test_le_module_des_demandes_est_mis_en_cache_a_l_installation, test_seule_une_fosa_porte_le_panneau_de_commande_hors_connexion

### `frps_project/urls.py` (29 l.)
- URL `admin/` -> urls :13
- URL `sw.js` -> pwa.service_worker  `service_worker` :15
- URL `manifest.webmanifest` -> pwa.manifeste  `manifeste` :16
- URL `hors-ligne/` -> pwa.hors_ligne  `hors_ligne` :17
- URL `.well-known/assetlinks.json` -> pwa.assetlinks  `assetlinks` :18
- URL `''` -> as_view() :19
- URL `login/` -> as_view()  `login` :20
- URL `logout/` -> as_view()  `logout` :21
- URL `catalogue/` -> include(catalogue.urls) :22
- URL `panier/` -> include(commandes.urls) :23
- URL `paiements/` -> include(paiements.urls) :24
- URL `notifications/` -> include(notifications.urls) :25
- URL `statistiques/` -> include(statistiques.urls) :26
- URL `reclamations/` -> include(reclamations.urls) :27

## notifications (2419 lignes)

### `notifications/admin.py` (67 l.)
- *admin* **DestinataireEmailAdmin** :7 — list_editable=actif, recoit_reclamations, recoit_commandes, recoit_rapports
- *admin* **SMSLogAdmin** :16
- *admin* **WhatsAppLogAdmin** :27
- *admin* **EmailLogAdmin** :38
- *admin* **NotificationAdmin** :49
- *admin* **PushSubscriptionAdmin** :60

### `notifications/backends.py` (284 l.)
- *classe* **SMSBackend**(ABC) :9 — Interface d'envoi de SMS. Une seule méthode à implémenter par backend.
  - methodes : send() :13
- *classe* **LogSMSBackend**(SMSBackend) :20 — Backend par défaut tant qu'aucune passerelle SMS réelle n'est branchée.
  - methodes : send() :27
- *classe* **TwilioSMSBackend**(SMSBackend) :32 — Envoi réel de SMS via Twilio.
  - methodes : send() :40
- *classe* **OrangeSMSBackend**(SMSBackend) :71 — Envoi réel de SMS via l'API Orange Developer (SMS API), pour une bien
  - methodes : _obtenir_jeton() :82, send() :107
- *classe* **MTNSMSBackend**(SMSBackend) :153 — Envoi réel de SMS via l'API MTN Developer (produit "SMS V2"), pour une
  - methodes : _obtenir_jeton() :173, send() :191
- *classe* **RealSMSBackend**(SMSBackend) :245 — Squelette générique pour une autre passerelle SMS réelle.
  - methodes : send() :252
- `verifier_statut_livraison_mtn(transaction_id)` :226 — Interroge l'API MTN (GET deliveryStatus) pour connaître le vrai statut de
- `get_sms_backend()` :273

### `notifications/context_processors.py` (24 l.)
- `notifications_non_lues(request)` :8 — Expose le nombre de notifications non lues du personnel FRPS connecté,

### `notifications/emails.py` (231 l.)
- `destinataires_personnel_frps()` :20 — Emails du personnel FRPS actif : tous les rôles SAUF les formations
- `fusionner_adresses(*listes)` :41 — Adresses sans doublon, la casse ne comptant pas (Jean@x.cm = jean@x.cm).
- `envoyer_email_nouvelle_commande(commande)` :87 — Envoie le récapitulatif de la commande, PDF joint, à tout le personnel FRPS.
- `envoyer_un_par_un(destinataires, sujet, corps, type_evenement, commande, pieces)` :121 — Un envoi par destinataire plutôt qu'un envoi groupé : une adresse invalide ne
- `envoyer_email_reclamation(reclamation, rouverte, message)` :154 — Prévient par e-mail les adresses cochées « Réclamations » dans Paramètres.
- `envoyer_email_test(adresse)` :221 — E-mail d'essai depuis Paramètres : prouve que l'adresse est bonne et que le

### `notifications/models.py` (199 l.)
- *enum* **TypeEvenement** :5 — NOUVELLE_COMMANDE, PAIEMENT_CONFIRME, COMMANDE_PRETE, RECLAMATION_RESOLUE, RECLAMATION, EMAIL_TEST
- *enum* **StatutEnvoi** :14 — ENVOYE, ECHEC
- *modele* **SMSLog** :19
  - champs : destinataire(Char), message(Text), type_evenement(Char choices=TypeEvenement.choices), statut_envoi(Char choices=StatutEnvoi.choices), commande(ForeignKey ->commandes.Commande related_name=sms_envoyes), date_envoi(DateTime), detail_erreur(Text), reference_externe(Char), statut_livraison(Char), date_statut_livraison(DateTime)
- *modele* **WhatsAppLog** :52 — Envoi du PDF de la commande validée vers les numéros WhatsApp configurés.
  - champs : destinataire(Char), commande(ForeignKey ->commandes.Commande related_name=whatsapp_envoyes), statut_envoi(Char choices=StatutEnvoi.choices), date_envoi(DateTime), detail_erreur(Text)
- *modele* **EmailLog** :72 — Envoi d'un email de notification au personnel FRPS, tracé au même titre que
  - champs : destinataire(Email), sujet(Char), type_evenement(Char choices=TypeEvenement.choices), statut_envoi(Char choices=StatutEnvoi.choices), commande(ForeignKey ->commandes.Commande related_name=emails_envoyes), date_envoi(DateTime), detail_erreur(Text)
- *modele* **Notification** :97 — Notification interne à l'application, gratuite et immédiate pour le
  - champs : role_cible(Char), type_evenement(Char choices=TypeEvenement.choices), message(Text), commande(ForeignKey ->commandes.Commande related_name=notifications_internes), lu(Boolean), date_creation(DateTime)
- *modele* **PushSubscription** :119 — Abonnement Web Push d'un navigateur/appareil (PWA ou APK installé) pour un
  - champs : user(ForeignKey ->settings.AUTH_USER_MODEL related_name=push_subscriptions), endpoint(URL), p256dh(Char), auth(Char), appareil_id(Char), date_creation(DateTime), date_confirmation(DateTime), date_dernier_envoi(DateTime), dernier_statut(Char)
- *modele* **DestinataireEmail** :166 — Adresse e-mail paramétrée par l'admin FRPS depuis l'application (Paramètres).
  - champs : email(Email), nom(Char), actif(Boolean), recoit_commandes(Boolean), recoit_reclamations(Boolean), recoit_rapports(Boolean), date_ajout(DateTime)
- *classe* **DestinataireEmailQuerySet**(QuerySet) :160
  - methodes : pour() :161

### `notifications/parametres.py` (45 l.)
- `ajouter_destinataire(email, nom, envois)` :20
- `modifier_destinataire(destinataire, actif, envois)` :34 — Enregistre les cases cochées d'une ligne. Une adresse sans aucun envoi coché ne

### `notifications/pdf.py` (131 l.)
- *classe* **CommandePDF**(FPDF) :37 — En-tête (mention République/Région/FRPS + logo) et pied de page (logos des
  - methodes : header() :42, footer() :68
- `generer_token_pdf(commande_id)` :24 — Jeton signé permettant de récupérer le PDF sans authentification (utilisé par Twilio).
- `verifier_token_pdf(commande_id, token)` :29
- `generer_pdf_commande(commande)` :83 — Génère le PDF récapitulatif d'une commande validée (pour envoi WhatsApp).

### `notifications/push.py` (152 l.)
- `_vapid()` :35 — py_vapid n'accepte pas directement une chaine PEM (voir Vapid.from_string,
- `envoyer_push_a_abonnement(abonnement, titre, corps, url)` :41 — Envoie une notification push à UN appareil.
- `_tracer(abonnement, statut)` :83 — Garde la trace du dernier envoi, affichée dans « Mes appareils ».
- `envoyer_push_a_utilisateur(user, titre, corps, url)` :110 — Envoie une notification push à tous les appareils abonnés de cet utilisateur.
- `envoyer_push_aux_utilisateurs(users, titre, corps, url)` :120 — Envoi en tâche de fond : ces notifications partent depuis la requête de
- *const* `_PEREMPTION_JOURS = 45` :26
- *const* `_DELAI_ENVOI_SECONDES = 10` :32

### `notifications/services.py` (248 l.)
- `_sans_accents(texte)` :17 — Retire les accents pour permettre l'encodage SMS GSM-7 (160 car./segment)
- `_formatter_lignes_complet(commande)` :91 — Détail complet des produits, sans contrainte de longueur (pour la notification
- `notifier_nouvelle_commande(commande)` :100
- `numero_international(numero)` :149 — « 6XX XX XX XX » saisi à la camerounaise → « +2376XXXXXXXX ». Twilio refuse un
- `notifier_commande_prete(commande)` :165 — SMS à la FOSA quand le personnel stock marque sa commande « prête ».
- `notifier_paiement_confirme(commande)` :182 — En pause depuis le retrait de l'étape paiement du parcours FOSA (2026-07-26) :
- `notifier_commande_validee_whatsapp(commande)` :218 — Envoie le PDF de la commande validée aux numéros WhatsApp configurés.
- *const* `_SMS_SEGMENT_MAX = 155` :56

### `notifications/tests.py` (381 l.)
- *classe* **PdfCommandeTests**(TestCase) :23
  - tests : test_token_valide_pour_la_bonne_commande_seulement, test_generer_pdf_commande_produit_des_octets_pdf, test_endpoint_pdf_public_sert_le_fichier_avec_un_token_valide, test_endpoint_pdf_refuse_un_token_invalide
- *classe* **NotificationInterneTests**(TestCase) :63
  - tests : test_confirmer_commande_cree_une_notification_pour_personnel_stock, test_paiement_confirme_cree_une_notification_pour_comptabilite, test_liste_ne_montre_que_les_notifications_du_role, test_formation_sanitaire_ne_peut_pas_voir_les_notifications, test_marquer_lu, test_un_role_ne_peut_pas_marquer_lu_la_notification_dun_autre_role
- *classe* **AbonnementPushTests**(TestCase) :133 — Un jeton d'abonnement tourne régulièrement côté navigateur. Sans ménage, la base
  - tests : test_le_meme_appareil_remplace_son_abonnement_au_lieu_den_ajouter_un, test_deux_appareils_distincts_gardent_chacun_leur_abonnement, test_rotation_du_jeton_par_le_service_worker_supprime_lancien_endpoint, test_le_service_worker_nefface_pas_lappareil_id_deja_connu, test_abonnement_jamais_reconfirme_supprime_sans_envoi, test_bouton_tester_nenvoie_qua_lappareil_choisi, test_on_ne_peut_ni_tester_ni_supprimer_lappareil_dun_autre, test_la_page_notifications_liste_les_appareils_de_lutilisateur, test_le_resultat_du_dernier_envoi_est_trace_sans_rajeunir_labonnement, test_un_envoi_qui_naboutit_pas_est_trace_injoignable, test_lenvoi_groupe_ne_bloque_pas_lappelant
- *classe* **EmailNouvelleCommandeTests**(TestCase) :293 — L'email part vers tout le personnel FRPS actif, jamais vers les FOSA :
  - tests : test_email_envoye_a_tout_le_personnel_frps_sauf_la_fosa, test_email_porte_le_pdf_et_le_detail_de_la_commande, test_chaque_envoi_est_trace, test_aucun_compte_avec_email_ne_fait_rien_planter, test_un_relais_smtp_en_panne_ne_fait_pas_echouer_la_commande

### `notifications/tests_parametres.py` (187 l.)
- *classe* **PageParametresEmailsTests**(TestCase) :28
  - tests : test_ajouter_une_adresse_avec_ses_envois, test_adresse_invalide_ou_sans_envoi_refusee, test_doublon_refuse, test_modifier_desactiver_supprimer, test_email_de_test, test_mode_test_signale_quand_les_emails_ne_partent_pas, test_pas_de_bandeau_quand_l_envoi_est_reel, test_reserve_a_l_admin, test_un_simple_get_ne_supprime_rien, test_le_menu_parametres_n_apparait_que_pour_l_admin
- *classe* **ListesDeDestinatairesTests**(TestCase) :99 — Les adresses paramétrées s'ajoutent aux comptes pour les commandes et le rapport ;
  - tests : test_commandes_comptes_plus_liste_sans_doublon_ni_inactif, test_rapport_admin_plus_liste
- *classe* **EmailReclamationTests**(TestCase) :121
  - tests : test_email_aux_seules_adresses_reclamations_avec_photos_et_lien, test_sans_adresse_rien_ne_part_et_la_reclamation_est_creee, test_un_relais_en_panne_n_empeche_pas_la_reclamation, test_email_a_la_reouverture_seulement, test_rappel_sur_la_page_des_reclamations_pour_l_admin

### `notifications/urls.py` (37 l.)
- URL `''` -> views.liste  `notifications:liste` :8
- URL `<int:notification_id>/lu/` -> views.marquer_lu  `notifications:marquer_lu` :9
- URL `tout-lu/` -> views.marquer_tout_lu  `notifications:marquer_tout_lu` :10
- URL `abonnement-push/` -> views.enregistrer_abonnement_push  `notifications:abonnement_push` :11
- URL `abonnement-push/<int:abonnement_id>/test/` -> views.tester_abonnement_push  `notifications:tester_abonnement_push` :12
- URL `abonnement-push/<int:abonnement_id>/supprimer/` -> views.supprimer_abonnement_push  `notifications:supprimer_abonnement_push` :13
- URL `parametres/emails/` -> views.parametres_emails  `notifications:parametres_emails` :18
- URL `parametres/emails/<int:destinataire_id>/modifier/` -> views.modifier_destinataire_email  `notifications:modifier_destinataire_email` :19
- URL `parametres/emails/<int:destinataire_id>/supprimer/` -> views.supprimer_destinataire_email  `notifications:supprimer_destinataire_email` :24
- URL `parametres/emails/<int:destinataire_id>/tester/` -> views.tester_destinataire_email  `notifications:tester_destinataire_email` :29
- URL `orange-dr/` -> views.orange_dr_callback  `notifications:orange_dr_callback` :34
- URL `twilio-dlr/` -> views.twilio_status_callback  `notifications:twilio_status_callback` :35

### `notifications/views.py` (314 l.)
- `liste(request)` :30 @personnel_frps_required
- `marquer_lu(request, notification_id)` :44 @personnel_frps_required @require_POST
- `marquer_tout_lu(request)` :53 @personnel_frps_required @require_POST
- `enregistrer_abonnement_push(request)` :61 @personnel_frps_required @require_POST — Reçoit l'abonnement Web Push créé côté navigateur (PushManager.subscribe)
- `tester_abonnement_push(request, abonnement_id)` :105 @personnel_frps_required @require_POST — Envoie une notification de test à UN appareil de l'utilisateur connecté.
- `supprimer_abonnement_push(request, abonnement_id)` :128 @personnel_frps_required @require_POST
- `orange_dr_callback(request)` :139 @csrf_exempt @require_POST — Reçoit le Delivery Receipt (DR) envoyé par Orange après l'envoi d'un SMS via
- `twilio_status_callback(request)` :179 @csrf_exempt @require_POST — Reçoit l'accusé de livraison (DLR) envoyé par Twilio après chaque SMS.
- `parametres_emails(request)` :213 @admin_frps_required
- `modifier_destinataire_email(request, destinataire_id)` :264 @admin_frps_required @require_POST
- `supprimer_destinataire_email(request, destinataire_id)` :279 @admin_frps_required @require_POST
- `tester_destinataire_email(request, destinataire_id)` :288 @admin_frps_required @require_POST
- `envoi_email_reel()` :309 — Faux en local (EMAIL_BACKEND_MODE=console, ou tests) : les e-mails sont alors

### `notifications/whatsapp.py` (119 l.)
- *classe* **WhatsAppBackend**(ABC) :9
  - methodes : send_document() :11
- *classe* **LogWhatsAppBackend**(WhatsAppBackend) :23 — Backend par défaut tant qu'aucune API WhatsApp réelle n'est branchée.
  - methodes : send_document() :26
- *classe* **TwilioWhatsAppBackend**(WhatsAppBackend) :33 — Envoi réel via l'API WhatsApp de Twilio.
  - methodes : send_document() :47
- *classe* **RealWhatsAppBackend**(WhatsAppBackend) :78 — Squelette pour l'API WhatsApp Business (Meta Cloud API).
  - methodes : send_document() :88
- `get_whatsapp_backend()` :112

## paiements (764 lignes)

### `paiements/admin.py` (36 l.)
- *admin* **ReglementPaiementInline** :6
- *admin* **PaiementAdmin** :22

### `paiements/gateways.py` (82 l.)
- *classe* **PaymentGateway**(ABC) :10
  - methodes : initiate_payment() :12, handle_callback() :17
- *classe* **MockOrangeMoneyGateway**(PaymentGateway) :22 — Simule Orange Money : confirme immédiatement le paiement.
  - methodes : initiate_payment() :29, handle_callback() :34
- *classe* **OrangeMoneyGateway**(PaymentGateway) :38 — Squelette d'intégration API Orange Money Cameroun (Web Payment).
  - methodes : initiate_payment() :47, handle_callback() :70
- `get_payment_gateway()` :77

### `paiements/models.py` (93 l.)
- *enum* **StatutPaiement** :8 — EN_ATTENTE, CONFIRME, ECHOUE
- *enum* **MethodePaiement** :14 — ORANGE_MONEY, MTN_MOMO, ESPECES, VIREMENT_BANCAIRE
- *enum* **EtatPaiement** :21 — NON_PAYEE, PARTIELLE, PAYEE
- *modele* **Paiement** :27 — Suivi du paiement effectué hors application (espèces remises au FRPS) — le
  - champs : commande(OneToOne ->commandes.Commande related_name=paiement), methode(Char choices=MethodePaiement.choices), montant(Decimal), statut(Char choices=StatutPaiement.choices), reference_transaction(Char), date_initiation(DateTime), date_confirmation(DateTime), montant_paye(Decimal), date_maj_paiement(DateTime), maj_par(ForeignKey ->settings.AUTH_USER_MODEL related_name=+)
  - methodes : etat() :56
- *modele* **ReglementPaiement** :64 — Un versement individuel (espèces) reçu pour une commande, saisi par le
  - champs : paiement(ForeignKey ->Paiement related_name=reglements), montant(Decimal), methode(Char choices=MethodePaiement.choices), date_paiement(Date), date_reglement(DateTime), saisi_par(ForeignKey ->settings.AUTH_USER_MODEL related_name=+)

### `paiements/services.py` (152 l.)
- `initier_paiement(commande)` :13 — Initie un paiement Orange Money (le client règle sur le compte Orange Money du FRPS).
- `payer_en_especes(commande)` :29 — Valide directement la commande en paiement espèces : aucune étape supplémentaire.
- `confirmer_paiement(paiement, succes)` :45
- `_valider_date_paiement(valeur_brute, commande)` :65 — Contrôle la date de règlement saisie à la main par la comptabilité.
- `mettre_a_jour_paiement(commande, montant_verse_brut, user, methode, date_paiement)` :95 — Saisie manuelle par le personnel comptabilité d'un nouveau versement reçu

### `paiements/tests.py` (231 l.)
- *classe* **PaiementWorkflowTests**(TestCase) :19
  - tests : test_confirmer_paiement_marque_commande_payee_et_notifie_comptabilite, test_paiement_echoue_ne_notifie_pas, test_confirmer_paiement_ne_declenche_plus_l_envoi_whatsapp_automatique, test_payer_en_especes_valide_directement_sans_etape_supplementaire
- *classe* **DateDeReglementTests**(TestCase) :69 — La FOSA règle un jour, la comptabilité saisit parfois bien plus tard. C'est la
  - tests : test_la_date_saisie_est_conservee_telle_quelle, test_sans_date_fournie_le_jour_meme_est_retenu, test_une_date_future_est_refusee, test_une_date_anterieure_a_la_commande_est_refusee, test_une_date_illisible_est_refusee, test_plusieurs_reglements_partiels_gardent_chacun_leur_date, test_le_virement_bancaire_est_un_moyen_accepte, test_le_formulaire_propose_la_date_et_les_quatre_moyens, test_l_historique_affiche_les_deux_dates
- *classe* **VersementsEnFrancsEntiersTests**(TestCase) :179 — Le total d'une commande est un nombre entier de FCFA : les versements aussi,
  - tests : test_la_commande_se_solde_avec_le_montant_affiche, test_un_versement_a_decimales_est_refuse, test_un_ancien_reglement_a_centimes_ne_laisse_pas_la_commande_partielle, test_le_formulaire_n_accepte_que_des_francs_entiers

### `paiements/urls.py` (16 l.)
- URL `gerer/` -> views.gerer_paiements  `paiements:gerer_paiements` :8
- URL `<int:commande_id>/` -> views.payer  `paiements:payer` :9
- URL `<int:commande_id>/initier/` -> views.initier  `paiements:initier` :10
- URL `<int:commande_id>/especes/` -> views.payer_especes  `paiements:payer_especes` :11
- URL `<int:commande_id>/confirmer-mock/` -> views.confirmer_mock  `paiements:confirmer_mock` :12
- URL `<int:commande_id>/succes/` -> views.succes  `paiements:succes` :13
- URL `<int:commande_id>/modifier/` -> views.modifier_paiement  `paiements:modifier_paiement` :14

### `paiements/views.py` (154 l.)
- `payer(request, commande_id)` :31 @formation_sanitaire_only_required
- `initier(request, commande_id)` :53 @formation_sanitaire_only_required @require_POST
- `payer_especes(request, commande_id)` :67 @formation_sanitaire_only_required @require_POST — Valide la commande en paiement espèces : aucune étape supplémentaire.
- `confirmer_mock(request, commande_id)` :86 @formation_sanitaire_only_required @require_POST — Simule le callback Orange Money (uniquement utile en mode mock/démo).
- `succes(request, commande_id)` :101 @formation_sanitaire_only_required
- `gerer_paiements(request)` :109 @personnel_frps_required — Liste consultable par tout le personnel FRPS (stock inclus, en lecture) ; seule
- `modifier_paiement(request, commande_id)` :124 @comptabilite_frps_required

## reclamations (842 lignes)

### `reclamations/admin.py` (39 l.)
- *admin* **MessageReclamationInline** :8
- *admin* **PhotoReclamationInline** :15
- *admin* **ReclamationAdmin** :32

### `reclamations/context_processors.py` (18 l.)
- `reclamations_non_lues(request)` :4 — Pastille du menu Réclamations, sur toutes les pages. `fiche_fosa` et non

### `reclamations/models.py` (105 l.)
- *enum* **MotifReclamation** :6 — PRODUIT_MANQUANT, QUANTITE, MAUVAIS_PRODUIT, ABIME_PERIME, RETARD, FACTURATION, AUTRE
- *enum* **StatutReclamation** :16 — OUVERTE, EN_COURS, RESOLUE
- *modele* **Reclamation** :22
  - champs : formation_sanitaire(ForeignKey ->accounts.FormationSanitaire related_name=reclamations), commande(ForeignKey ->commandes.Commande related_name=reclamations), motif(Char choices=MotifReclamation.choices), description(Text), statut(Char choices=StatutReclamation.choices), traitee_par(ForeignKey ->settings.AUTH_USER_MODEL related_name=+), date_creation(DateTime), date_activite(DateTime), date_resolution(DateTime), non_lue_frps(Boolean), non_lue_fosa(Boolean)
  - methodes : est_close() :56
- *modele* **MessageReclamation** :60
  - champs : reclamation(ForeignKey ->Reclamation related_name=messages), auteur(ForeignKey ->settings.AUTH_USER_MODEL related_name=+), de_la_fosa(Boolean), texte(Text), date(DateTime)
- *modele* **PhotoReclamation** :76 — Photo jointe à une réclamation (produit abîmé, colis ouvert, bon de livraison…).
  - champs : reclamation(ForeignKey ->Reclamation related_name=photos), message(ForeignKey ->MessageReclamation related_name=photos), contenu(Binary), largeur(PositiveInteger), hauteur(PositiveInteger), date(DateTime)
  - methodes : taille_ko() :102

### `reclamations/services.py` (237 l.)
- `preparer_photo(fichier)` :25 — Vérifie qu'un fichier envoyé est bien une image et la réduit : grand côté à
- `_preparer_photos(fichiers)` :60 — Prépare toutes les photos AVANT d'écrire quoi que ce soit : une photo refusée
- `creer_reclamation(formation_sanitaire, auteur, motif, description, commande, photos)` :83
- `message_fosa(reclamation, auteur, texte, photos)` :115 — Message de la FOSA. Sur une réclamation résolue, il la rouvre : la FOSA
- `_envoyer_email(reclamation, rouverte, message)` :148 — Hors transaction et sans jamais lever : la réclamation est enregistrée, un
- `reponse_frps(reclamation, auteur, texte, statut, photos)` :159 — Réponse et/ou changement de statut par le personnel FRPS. La FOSA est prévenue
- `marquer_lue(reclamation, par_la_fosa)` :198
- `_prevenir_personnel(titre, corps, reclamation)` :205 — Push à tout le personnel FRPS actif, comme pour une nouvelle commande.
- *const* `LONGUEUR_MAX_TEXTE = 4000` :14
- *const* `PHOTOS_MAX_PAR_ENVOI = 3` :18
- *const* `PIXELS_MAX = 40000000` :20
- *const* `COTE_MAX = 1600` :21
- *const* `QUALITE_JPEG = 80` :22

### `reclamations/tests.py` (247 l.)
- *classe* **ReclamationTests**(TestCase) :18
  - tests : test_la_fosa_cree_une_reclamation_sur_sa_commande, test_sans_commande_precise_c_est_accepte, test_description_vide_refusee, test_motif_inconnu_refuse, test_la_commande_d_une_autre_fosa_est_refusee, test_le_personnel_ne_cree_pas_de_reclamation, test_une_fosa_ne_voit_pas_les_reclamations_d_une_autre, test_le_personnel_voit_toutes_les_reclamations_a_traiter, test_non_connecte_renvoye_a_la_connexion, test_reponse_du_frps_visible_et_signalee_a_la_fosa, test_resolution_previent_la_fosa_par_sms, test_reponse_vide_sans_changement_refusee, test_un_message_de_la_fosa_rouvre_une_reclamation_resolue, test_la_fosa_ne_peut_pas_changer_le_statut, test_supprimer_la_commande_garde_la_reclamation
- *classe* **PhotosReclamationTests**(TestCase) :167
  - tests : test_photos_jointes_a_la_creation_et_reduites, test_png_transparent_converti_sur_fond_blanc, test_un_faux_fichier_image_est_refuse_sans_rien_creer, test_plus_de_trois_photos_refusees, test_message_avec_photo_seule_accepte, test_le_frps_peut_joindre_une_photo, test_photo_servie_au_proprietaire_et_au_personnel_seulement, test_la_page_affiche_les_vignettes

### `reclamations/urls.py` (14 l.)
- URL `''` -> views.liste  `reclamations:liste` :8
- URL `nouvelle/` -> views.nouvelle  `reclamations:nouvelle` :9
- URL `<int:reclamation_id>/` -> views.detail  `reclamations:detail` :10
- URL `<int:reclamation_id>/repondre/` -> views.repondre  `reclamations:repondre` :11
- URL `photo/<int:photo_id>/` -> views.photo  `reclamations:photo` :12

### `reclamations/views.py` (182 l.)
- `_reclamations_visibles(request)` :17 — La FOSA ne voit que les siennes ; le personnel FRPS les voit toutes.
- `_compte_valide(view_func)` :25 — Connecté, et pas un compte FOSA sans fiche (il ferait planter les requêtes).
- `liste(request)` :40 @_compte_valide
- `nouvelle(request)` :79 @formation_sanitaire_only_required
- `detail(request, reclamation_id)` :129 @_compte_valide
- `repondre(request, reclamation_id)` :153 @_compte_valide @require_POST
- `photo(request, photo_id)` :174 @_compte_valide — Sert une photo jointe, avec les mêmes droits que la réclamation : la FOSA ne

## statistiques (603 lignes)

### `statistiques/management/commands/envoyer_rapport.py` (33 l.)
- *classe* **Command**(BaseCommand) :6 — Envoie le rapport d'activité périodique par email aux comptes admin actifs
  - methodes : add_arguments() :18, handle() :25

### `statistiques/rapports.py` (92 l.)
- `destinataires_rapport()` :57 — Comptes admin actifs avec un email renseigné (l'admin supervise tout), plus les
- `envoyer_rapport_periodique(jours, destinataires)` :69 — Génère et envoie le rapport d'activité des `jours` derniers jours aux

### `statistiques/services.py` (70 l.)
- `donnees_tableau_de_bord(debut, fin)` :10 — Rassemble les indicateurs du tableau de bord (statistiques:index) pour une

### `statistiques/tests.py` (80 l.)
- *classe* **StatistiquesTests**(TestCase) :16 — Les chiffres ne comptent que ce qui a réellement été servi : ni les paniers,
  - tests : test_tableau_de_bord_ne_compte_que_le_servi, test_pages_ouvertes_au_personnel, test_pages_fermees_aux_fosa, test_statistiques_par_produit, test_export_excel_par_produit, test_export_excel_par_fosa

### `statistiques/urls.py` (14 l.)
- URL `''` -> views.index  `statistiques:index` :8
- URL `produit/` -> views.par_produit  `statistiques:par_produit` :9
- URL `formation-sanitaire/` -> views.par_fosa  `statistiques:par_fosa` :10
- URL `district/` -> views.par_district  `statistiques:par_district` :11
- URL `stock/` -> views.stock  `statistiques:stock` :12

### `statistiques/views.py` (314 l.)
- `index(request)` :40 @personnel_frps_required
- `par_produit(request)` :46 @personnel_frps_required
- `par_fosa(request)` :102 @personnel_frps_required
- `par_district(request)` :156 @personnel_frps_required
- `stock(request)` :213 @personnel_frps_required

## stock_sync (165 lignes)

### `stock_sync/connectors.py` (113 l.)
- *classe* **StockConnector**(ABC) :7 — Source du stock. Retourne une liste de dicts avec les clés :
  - methodes : fetch_produits() :13
- *classe* **MockStockConnector**(StockConnector) :17 — Données d'exemple, utilisées tant que l'accès au SQL Server du FRPS
  - methodes : fetch_produits() :22
- *classe* **SageSQLServerConnector**(StockConnector) :62 — Connexion en lecture seule au SQL Server du FRPS (Sage Gescom).
  - methodes : fetch_produits() :75
- `get_stock_connector()` :108

### `stock_sync/management/commands/sync_stock.py` (36 l.)
- *classe* **Command**(BaseCommand) :8
  - methodes : handle() :12

## Commandes de gestion

- `manage.py ensure_admin` — `accounts/management/commands/ensure_admin.py` — Crée le superutilisateur admin FRPS depuis les variables d'environnement, si absent.
- `manage.py import_fosa` — `accounts/management/commands/import_fosa.py` — Importe le référentiel FOSA depuis accounts/data/fosa_nord.csv
- `manage.py seed_demo` — `accounts/management/commands/seed_demo.py` — Crée des comptes de démo : une formation sanitaire et du personnel FRPS (stock + comptabil
- `manage.py import_catalogue` — `catalogue/management/commands/import_catalogue.py` — Importe le catalogue depuis catalogue/data/produits_magasin_principal.csv
- `manage.py import_rayons` — `catalogue/management/commands/import_rayons.py` — Crée les rayons et rattache les produits depuis catalogue/data/rayons_classification.csv
- `manage.py update_stock` — `catalogue/management/commands/update_stock.py` — Met à jour prix_unitaire/stock_disponible depuis un fichier CSV d'actualisation
- `manage.py envoyer_rapport` — `statistiques/management/commands/envoyer_rapport.py` — Envoie le rapport d'activité périodique par email
- `manage.py sync_stock` — `stock_sync/management/commands/sync_stock.py` — Synchronise le catalogue local depuis la source de stock (SQL Server FRPS ou mock).

## Gabarits

`templates/accounts/login.html`, `templates/base.html`, `templates/catalogue/_fiche_produit.html`, `templates/catalogue/_liste_promotions.html`, `templates/catalogue/gerer_promotions.html`, `templates/catalogue/importer.html`, `templates/catalogue/liste.html`, `templates/catalogue/promotions.html`, `templates/commandes/_actions_suivi.html`, `templates/commandes/_badge_etape.html`, `templates/commandes/_badge_paiement.html`, `templates/commandes/detail.html`, `templates/commandes/historique.html`, `templates/commandes/panier.html`, `templates/commandes/suivi.html`, `templates/notifications/liste.html`, `templates/notifications/parametres_emails.html`, `templates/paiements/gerer.html`, `templates/paiements/modifier.html`, `templates/paiements/payer.html`, `templates/paiements/succes.html`, `templates/pwa/hors_ligne.html`, `templates/pwa/manifest.webmanifest`, `templates/pwa/sw.js`, `templates/reclamations/_badge_statut.html`, `templates/reclamations/_champ_photos.html`, `templates/reclamations/_photos.html`, `templates/reclamations/detail.html`, `templates/reclamations/liste.html`, `templates/reclamations/nouvelle.html`, `templates/statistiques/index.html`, `templates/statistiques/par_district.html`, `templates/statistiques/par_fosa.html`, `templates/statistiques/par_produit.html`, `templates/statistiques/stock.html`

