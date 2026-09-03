# Carte du code — commande-frps

<!-- Genere par la skill carte-du-code le 2026-09-03. NE PAS EDITER A LA MAIN : relancer scripts/generer_carte.py. -->

**Lire ce fichier avant d'explorer le depot.** Il donne `fichier:ligne` pour chaque modele, URL, vue et fonction.

9 modules · 13 modeles · 46 URLs · 95 fonctions · 20 gabarits · 5152 lignes de Python

## accounts (339 lignes)

### `accounts/admin.py` (30 l.)
- *admin* **FormationSanitaireAdmin** :25
- *classe* **UserAdmin**(BaseUserAdmin) :8 — Utilisé par un admin FRPS pour créer les comptes (formations sanitaires et personnel).

### `accounts/decorators.py` (83 l.)
- `formation_sanitaire_required(view_func)` :10 — Réservé aux formations sanitaires. L'admin FRPS a accès à tout (y compris
- `personnel_frps_required(view_func)` :26
- `admin_frps_required(view_func)` :37 — Réservé au compte super admin FRPS (role=admin). Utilisé pour les actions
- `comptabilite_frps_required(view_func)` :51 — Réservé au personnel comptabilité et à l'admin FRPS. Utilisé pour la mise à
- `formation_sanitaire_only_required(view_func)` :66 — Réservé aux comptes ayant un vrai profil FormationSanitaire (panier, commandes,

### `accounts/management/commands/ensure_admin.py` (32 l.)
- *classe* **Command**(BaseCommand) :7 — Crée le compte admin FRPS s'il n'existe pas encore, à partir des variables

### `accounts/management/commands/import_fosa.py` (71 l.)
- *classe* **Command**(BaseCommand) :13 — Importe le référentiel des formations sanitaires (région/district/nom) depuis

### `accounts/management/commands/seed_demo.py` (36 l.)
- *classe* **Command**(BaseCommand) :6

### `accounts/models.py` (61 l.)
- *enum* **Role** :5 — ADMIN, FORMATION_SANITAIRE, PERSONNEL_STOCK, PERSONNEL_COMPTABILITE
- *modele* **User** :16
  - champs : role(Char choices=Role.choices), telephone(Char)
  - methodes : is_formation_sanitaire() :25, is_admin_frps() :29, is_personnel_stock() :33, is_personnel_comptabilite() :37
- *modele* **FormationSanitaire** :44
  - champs : user(OneToOne ->User related_name=formation_sanitaire), nom(Char), region(Char), district(Char), adresse(Char), telephone_contact(Char), actif(Boolean), date_creation(DateTime)

### `accounts/views.py` (22 l.)
- *classe* **LoginView**(LoginView) :8 — Redirige après connexion selon le rôle : catalogue pour les formations

## catalogue (578 lignes)

### `catalogue/admin.py` (20 l.)
- *admin* **RayonAdmin** :7 — list_editable=ordre
- *admin* **ProduitAdmin** :14 — list_editable=prix_unitaire, stock_disponible, magasin, rayon, actif

### `catalogue/management/commands/import_catalogue.py` (70 l.)
- *classe* **Command**(BaseCommand) :21 — Importe/actualise le catalogue depuis catalogue/data/produits_magasin_principal.csv

### `catalogue/management/commands/import_rayons.py` (63 l.)
- *classe* **Command**(BaseCommand) :23 — Crée/actualise les rayons puis rattache les produits selon

### `catalogue/management/commands/update_stock.py` (131 l.)
- *classe* **Command**(BaseCommand) :72 — Met à jour prix_unitaire/stock_disponible depuis un fichier CSV fourni par
- `_read_updates_with_code_sage(path)` :23 — Fichier avec code_sage (colonnes code_sage;nom;...;prix_unitaire;stock_disponible,
- `_read_updates_by_position(update_csv)` :45 — Fichier sans code_sage (colonnes nom;prix_unitaire;stock_disponible). Le nom seul

### `catalogue/models.py` (84 l.)
- *enum* **Magasin** :11 — PRINCIPAL, UCPC, AUTRE
- *modele* **Rayon** :17 — Rayon de classification du catalogue (ex. Injectables, Comprimés).
  - champs : slug(Slug), nom(Char), icone(Char), ordre(PositiveSmallInteger)
- *modele* **Produit** :37 — Catalogue saisi et maintenu manuellement par l'admin FRPS via l'admin Django
  - champs : code_sage(Char), nom(Char), unite(Char), prix_unitaire(Decimal), stock_disponible(PositiveInteger), magasin(Char choices=Magasin.choices), actif(Boolean), derniere_synchro(DateTime), rayon(ForeignKey ->Rayon related_name=produits)
  - methodes : en_stock() :69, niveau_stock() :73
- *const* `SEUIL_STOCK_CRITIQUE = 10` :7
- *const* `SEUIL_STOCK_FAIBLE = 50` :8

### `catalogue/urls.py` (11 l.)
- URL `''` -> views.liste  `catalogue:liste` :8
- URL `importer/` -> views.importer_produits  `catalogue:importer` :9

### `catalogue/views.py` (195 l.)
- `liste(request)` :16 @formation_sanitaire_required
- `_lire_fichier_produits(fichier)` :85 — Lit un classeur Excel dont l'en-tête contient une colonne code produit
- `importer_produits(request)` :133 @admin_frps_required

## commandes (598 lignes)

### `commandes/admin.py` (20 l.)
- *admin* **LigneCommandeInline** :6
- *admin* **CommandeAdmin** :14

### `commandes/context_processors.py` (18 l.)
- `panier_resume(request)` :4 — Nombre de lignes du panier en cours, pour le badge de la navbar : sans lui,

### `commandes/models.py` (75 l.)
- *enum* **StatutCommande** :7 — BROUILLON, CONFIRMEE, PAYEE, ANNULEE
- *modele* **Commande** :14
  - champs : formation_sanitaire(ForeignKey ->accounts.FormationSanitaire related_name=commandes), statut(Char choices=StatutCommande.choices), montant_total(Decimal), date_creation(DateTime), date_confirmation(DateTime)
  - methodes : recalculer_montant() :31, montant_paye() :38, solde_restant() :43, etat_paiement() :47
- *modele* **LigneCommande** :56
  - champs : commande(ForeignKey ->Commande related_name=lignes), produit(ForeignKey ->catalogue.Produit related_name=lignes_commande), quantite(PositiveInteger), prix_unitaire_snapshot(Decimal)
  - methodes : sous_total() :71

### `commandes/services.py` (127 l.)
- *classe* **StockInsuffisantError**(Exception) :14
- `get_panier(formation_sanitaire)` :18 — Retourne le panier (commande brouillon) en cours, en crée un si besoin.
- `ajouter_produit(commande, produit, quantite)` :28
- `retirer_produit(commande, produit)` :50
- `confirmer_commande(commande)` :55 — Verrouille la commande, débite le stock, notifie le personnel FRPS chargé du stock.
- `supprimer_commande(commande)` :92 — Supprime une commande et remet en stock ce qu'elle avait débité.

### `commandes/tests.py` (173 l.)
- *classe* **CommandeWorkflowTests**(TestCase) :15
  - tests : test_ajouter_produit_respecte_le_stock, test_confirmer_commande_notifie_personnel_stock, test_confirmer_panier_vide_leve_une_erreur
- *classe* **TelechargerPdfTests**(TestCase) :51
  - tests : test_le_proprietaire_peut_telecharger_le_pdf, test_un_autre_utilisateur_ne_peut_pas_telecharger
- *classe* **SupprimerCommandeTests**(TestCase) :82 — Suppression d'une commande validée par erreur par une FOSA, réservée à l'admin.
  - tests : test_supprimer_une_commande_confirmee_remet_le_stock, test_supprimer_un_brouillon_ne_gonfle_pas_le_stock, test_admin_peut_supprimer_via_le_bouton, test_personnel_non_admin_ne_peut_pas_supprimer, test_fosa_ne_peut_pas_supprimer_sa_propre_commande, test_un_simple_GET_ne_supprime_rien, test_le_bouton_n_apparait_que_pour_l_admin

### `commandes/urls.py` (20 l.)
- URL `''` -> views.panier  `commandes:panier` :8
- URL `ajouter/<int:produit_id>/` -> views.ajouter  `commandes:ajouter` :9
- URL `modifier-quantite/<int:produit_id>/` -> views.modifier_quantite  `commandes:modifier_quantite` :10
- URL `retirer/<int:produit_id>/` -> views.retirer  `commandes:retirer` :11
- URL `confirmer/` -> views.confirmer  `commandes:confirmer` :12
- URL `historique/` -> views.historique  `commandes:historique` :13
- URL `<int:commande_id>/pdf/<str:token>/` -> views.pdf_commande  `commandes:pdf` :14
- URL `<int:commande_id>/telecharger/` -> views.telecharger_pdf  `commandes:telecharger_pdf` :15
- URL `<int:commande_id>/telecharger-staff/` -> views.telecharger_pdf_staff  `commandes:telecharger_pdf_staff` :16
- URL `<int:commande_id>/supprimer/` -> views.supprimer  `commandes:supprimer` :17
- URL `<int:commande_id>/` -> views.detail  `commandes:detail` :18

### `commandes/views.py` (165 l.)
- `panier(request)` :19 @formation_sanitaire_only_required
- `ajouter(request, produit_id)` :26 @formation_sanitaire_only_required @require_POST
- `modifier_quantite(request, produit_id)` :40 @formation_sanitaire_only_required @require_POST — Corrige la quantité d'une ligne directement depuis le panier : il fallait
- `retirer(request, produit_id)` :71 @formation_sanitaire_only_required @require_POST
- `confirmer(request)` :81 @formation_sanitaire_only_required @require_POST
- `historique(request)` :95 @formation_sanitaire_only_required
- `detail(request, commande_id)` :106 @formation_sanitaire_only_required
- `telecharger_pdf(request, commande_id)` :116 @formation_sanitaire_only_required — Téléchargement du PDF par la FOSA elle-même (pour l'enregistrer ou le partager,
- `telecharger_pdf_staff(request, commande_id)` :129 @personnel_frps_required — Téléchargement du PDF par le personnel FRPS (depuis la page notifications),
- `pdf_commande(request, commande_id, token)` :139 — Sert le PDF de la commande sans authentification : accès protégé par un jeton
- `supprimer(request, commande_id)` :153 @admin_frps_required @require_POST — Suppression d'une commande par l'admin FRPS, avec remise en stock.

## deploy (26 lignes)

## frps_project (352 lignes)

### `frps_project/formatage.py` (15 l.)
- `formater_montant(valeur)` :1 — Montant arrondi (sans décimales), séparateur de milliers. Pour un prix
- `formater_prix(valeur)` :7 — Prix unitaire : décimales conservées, séparateur de milliers ajouté.

### `frps_project/pwa.py` (81 l.)
- `service_worker(request)` :29 @require_GET @cache_control — `no-cache` : le navigateur doit revalider le fichier pour voir les mises à jour.
- `manifeste(request)` :41 @require_GET
- `assetlinks(request)` :46 @require_GET — Lien vérifié entre le domaine et l'application Android (Digital Asset Links).
- `hors_ligne(request)` :73 @require_GET — Page de repli affichée quand une page non encore consultée est demandée sans réseau.

### `frps_project/settings.py` (228 l.)
- *const* `AUTH_USER_MODEL = 'accounts.User'` :51
- *const* `ROOT_URLCONF = 'frps_project.urls'` :64
- *const* `WSGI_APPLICATION = 'frps_project.wsgi.application'` :83
- *const* `LANGUAGE_CODE = 'fr-fr'` :118
- *const* `TIME_ZONE = 'Africa/Douala'` :120
- *const* `USE_I18N = True` :122
- *const* `USE_THOUSAND_SEPARATOR = True` :126
- *const* `USE_TZ = True` :128
- *const* `STATIC_URL = 'static/'` :134
- *const* `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'` :142
- *const* `LOGIN_URL = 'login'` :144
- *const* `LOGIN_REDIRECT_URL = 'catalogue:liste'` :145
- *const* `LOGOUT_REDIRECT_URL = 'login'` :146

### `frps_project/urls.py` (28 l.)
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

## notifications (1876 lignes)

### `notifications/admin.py` (58 l.)
- *admin* **SMSLogAdmin** :7
- *admin* **WhatsAppLogAdmin** :18
- *admin* **EmailLogAdmin** :29
- *admin* **NotificationAdmin** :40
- *admin* **PushSubscriptionAdmin** :51

### `notifications/backends.py` (284 l.)
- *classe* **SMSBackend**(ABC) :9 — Interface d'envoi de SMS. Une seule méthode à implémenter par backend.
- *classe* **LogSMSBackend**(SMSBackend) :20 — Backend par défaut tant qu'aucune passerelle SMS réelle n'est branchée.
- *classe* **TwilioSMSBackend**(SMSBackend) :32 — Envoi réel de SMS via Twilio.
- *classe* **OrangeSMSBackend**(SMSBackend) :71 — Envoi réel de SMS via l'API Orange Developer (SMS API), pour une bien
- *classe* **MTNSMSBackend**(SMSBackend) :153 — Envoi réel de SMS via l'API MTN Developer (produit "SMS V2"), pour une
- *classe* **RealSMSBackend**(SMSBackend) :245 — Squelette générique pour une autre passerelle SMS réelle.
- `verifier_statut_livraison_mtn(transaction_id)` :226 — Interroge l'API MTN (GET deliveryStatus) pour connaître le vrai statut de
- `get_sms_backend()` :273

### `notifications/context_processors.py` (24 l.)
- `notifications_non_lues(request)` :8 — Expose le nombre de notifications non lues du personnel FRPS connecté,

### `notifications/emails.py` (132 l.)
- `destinataires_personnel_frps()` :20 — Emails du personnel FRPS actif : tous les rôles SAUF les formations
- `envoyer_email_nouvelle_commande(commande)` :77 — Envoie le récapitulatif de la commande, PDF joint, à tout le personnel FRPS.

### `notifications/models.py` (154 l.)
- *enum* **TypeEvenement** :5 — NOUVELLE_COMMANDE, PAIEMENT_CONFIRME
- *enum* **StatutEnvoi** :10 — ENVOYE, ECHEC
- *modele* **SMSLog** :15
  - champs : destinataire(Char), message(Text), type_evenement(Char choices=TypeEvenement.choices), statut_envoi(Char choices=StatutEnvoi.choices), commande(ForeignKey ->commandes.Commande related_name=sms_envoyes), date_envoi(DateTime), detail_erreur(Text), reference_externe(Char), statut_livraison(Char), date_statut_livraison(DateTime)
- *modele* **WhatsAppLog** :48 — Envoi du PDF de la commande validée vers les numéros WhatsApp configurés.
  - champs : destinataire(Char), commande(ForeignKey ->commandes.Commande related_name=whatsapp_envoyes), statut_envoi(Char choices=StatutEnvoi.choices), date_envoi(DateTime), detail_erreur(Text)
- *modele* **EmailLog** :68 — Envoi d'un email de notification au personnel FRPS, tracé au même titre que
  - champs : destinataire(Email), sujet(Char), type_evenement(Char choices=TypeEvenement.choices), statut_envoi(Char choices=StatutEnvoi.choices), commande(ForeignKey ->commandes.Commande related_name=emails_envoyes), date_envoi(DateTime), detail_erreur(Text)
- *modele* **Notification** :93 — Notification interne à l'application, gratuite et immédiate pour le
  - champs : role_cible(Char), type_evenement(Char choices=TypeEvenement.choices), message(Text), commande(ForeignKey ->commandes.Commande related_name=notifications_internes), lu(Boolean), date_creation(DateTime)
- *modele* **PushSubscription** :115 — Abonnement Web Push d'un navigateur/appareil (PWA ou APK installé) pour un
  - champs : user(ForeignKey ->settings.AUTH_USER_MODEL related_name=push_subscriptions), endpoint(URL), p256dh(Char), auth(Char), appareil_id(Char), date_creation(DateTime), date_confirmation(DateTime), date_dernier_envoi(DateTime), dernier_statut(Char)

### `notifications/pdf.py` (131 l.)
- *classe* **CommandePDF**(FPDF) :37 — En-tête (mention République/Région/FRPS + logo) et pied de page (logos des
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

### `notifications/services.py` (215 l.)
- `_sans_accents(texte)` :17 — Retire les accents pour permettre l'encodage SMS GSM-7 (160 car./segment)
- `_formatter_lignes_complet(commande)` :91 — Détail complet des produits, sans contrainte de longueur (pour la notification
- `notifier_nouvelle_commande(commande)` :100
- `notifier_paiement_confirme(commande)` :149 — En pause depuis le retrait de l'étape paiement du parcours FOSA (2026-07-26) :
- `notifier_commande_validee_whatsapp(commande)` :185 — Envoie le PDF de la commande validée aux numéros WhatsApp configurés.
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

### `notifications/urls.py` (21 l.)
- URL `''` -> views.liste  `notifications:liste` :8
- URL `<int:notification_id>/lu/` -> views.marquer_lu  `notifications:marquer_lu` :9
- URL `tout-lu/` -> views.marquer_tout_lu  `notifications:marquer_tout_lu` :10
- URL `abonnement-push/` -> views.enregistrer_abonnement_push  `notifications:abonnement_push` :11
- URL `abonnement-push/<int:abonnement_id>/test/` -> views.tester_abonnement_push  `notifications:tester_abonnement_push` :12
- URL `abonnement-push/<int:abonnement_id>/supprimer/` -> views.supprimer_abonnement_push  `notifications:supprimer_abonnement_push` :13
- URL `orange-dr/` -> views.orange_dr_callback  `notifications:orange_dr_callback` :18
- URL `twilio-dlr/` -> views.twilio_status_callback  `notifications:twilio_status_callback` :19

### `notifications/views.py` (205 l.)
- `liste(request)` :28 @personnel_frps_required
- `marquer_lu(request, notification_id)` :42 @personnel_frps_required @require_POST
- `marquer_tout_lu(request)` :51 @personnel_frps_required @require_POST
- `enregistrer_abonnement_push(request)` :59 @personnel_frps_required @require_POST — Reçoit l'abonnement Web Push créé côté navigateur (PushManager.subscribe)
- `tester_abonnement_push(request, abonnement_id)` :103 @personnel_frps_required @require_POST — Envoie une notification de test à UN appareil de l'utilisateur connecté.
- `supprimer_abonnement_push(request, abonnement_id)` :126 @personnel_frps_required @require_POST
- `orange_dr_callback(request)` :137 @csrf_exempt @require_POST — Reçoit le Delivery Receipt (DR) envoyé par Orange après l'envoi d'un SMS via
- `twilio_status_callback(request)` :177 @csrf_exempt @require_POST — Reçoit l'accusé de livraison (DLR) envoyé par Twilio après chaque SMS.

### `notifications/whatsapp.py` (119 l.)
- *classe* **WhatsAppBackend**(ABC) :9
- *classe* **LogWhatsAppBackend**(WhatsAppBackend) :23 — Backend par défaut tant qu'aucune API WhatsApp réelle n'est branchée.
- *classe* **TwilioWhatsAppBackend**(WhatsAppBackend) :33 — Envoi réel via l'API WhatsApp de Twilio.
- *classe* **RealWhatsAppBackend**(WhatsAppBackend) :78 — Squelette pour l'API WhatsApp Business (Meta Cloud API).
- `get_whatsapp_backend()` :112

## paiements (701 lignes)

### `paiements/admin.py` (36 l.)
- *admin* **ReglementPaiementInline** :6
- *admin* **PaiementAdmin** :22

### `paiements/gateways.py` (82 l.)
- *classe* **PaymentGateway**(ABC) :10
- *classe* **MockOrangeMoneyGateway**(PaymentGateway) :22 — Simule Orange Money : confirme immédiatement le paiement.
- *classe* **OrangeMoneyGateway**(PaymentGateway) :38 — Squelette d'intégration API Orange Money Cameroun (Web Payment).
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

### `paiements/services.py` (146 l.)
- `initier_paiement(commande)` :12 — Initie un paiement Orange Money (le client règle sur le compte Orange Money du FRPS).
- `payer_en_especes(commande)` :28 — Valide directement la commande en paiement espèces : aucune étape supplémentaire.
- `confirmer_paiement(paiement, succes)` :44
- `_valider_date_paiement(valeur_brute, commande)` :64 — Contrôle la date de règlement saisie à la main par la comptabilité.
- `mettre_a_jour_paiement(commande, montant_verse_brut, user, methode, date_paiement)` :94 — Saisie manuelle par le personnel comptabilité d'un nouveau versement reçu

### `paiements/tests.py` (175 l.)
- *classe* **PaiementWorkflowTests**(TestCase) :18
  - tests : test_confirmer_paiement_marque_commande_payee_et_notifie_comptabilite, test_paiement_echoue_ne_notifie_pas, test_confirmer_paiement_ne_declenche_plus_l_envoi_whatsapp_automatique, test_payer_en_especes_valide_directement_sans_etape_supplementaire
- *classe* **DateDeReglementTests**(TestCase) :68 — La FOSA règle un jour, la comptabilité saisit parfois bien plus tard. C'est la
  - tests : test_la_date_saisie_est_conservee_telle_quelle, test_sans_date_fournie_le_jour_meme_est_retenu, test_une_date_future_est_refusee, test_une_date_anterieure_a_la_commande_est_refusee, test_une_date_illisible_est_refusee, test_plusieurs_reglements_partiels_gardent_chacun_leur_date, test_le_virement_bancaire_est_un_moyen_accepte, test_le_formulaire_propose_la_date_et_les_quatre_moyens, test_l_historique_affiche_les_deux_dates

### `paiements/urls.py` (16 l.)
- URL `gerer/` -> views.gerer_paiements  `paiements:gerer_paiements` :8
- URL `<int:commande_id>/` -> views.payer  `paiements:payer` :9
- URL `<int:commande_id>/initier/` -> views.initier  `paiements:initier` :10
- URL `<int:commande_id>/especes/` -> views.payer_especes  `paiements:payer_especes` :11
- URL `<int:commande_id>/confirmer-mock/` -> views.confirmer_mock  `paiements:confirmer_mock` :12
- URL `<int:commande_id>/succes/` -> views.succes  `paiements:succes` :13
- URL `<int:commande_id>/modifier/` -> views.modifier_paiement  `paiements:modifier_paiement` :14

### `paiements/views.py` (153 l.)
- `payer(request, commande_id)` :30 @formation_sanitaire_only_required
- `initier(request, commande_id)` :52 @formation_sanitaire_only_required @require_POST
- `payer_especes(request, commande_id)` :66 @formation_sanitaire_only_required @require_POST — Valide la commande en paiement espèces : aucune étape supplémentaire.
- `confirmer_mock(request, commande_id)` :85 @formation_sanitaire_only_required @require_POST — Simule le callback Orange Money (uniquement utile en mode mock/démo).
- `succes(request, commande_id)` :100 @formation_sanitaire_only_required
- `gerer_paiements(request)` :108 @personnel_frps_required — Liste consultable par tout le personnel FRPS (stock inclus, en lecture) ; seule
- `modifier_paiement(request, commande_id)` :123 @comptabilite_frps_required

## statistiques (517 lignes)

### `statistiques/management/commands/envoyer_rapport.py` (33 l.)
- *classe* **Command**(BaseCommand) :6 — Envoie le rapport d'activité périodique par email aux comptes admin actifs

### `statistiques/rapports.py` (86 l.)
- `destinataires_rapport()` :55 — Comptes admin actifs avec un email renseigné. Reproduit le même filtre que
- `envoyer_rapport_periodique(jours, destinataires)` :63 — Génère et envoie le rapport d'activité des `jours` derniers jours aux

### `statistiques/services.py` (70 l.)
- `donnees_tableau_de_bord(debut, fin)` :10 — Rassemble les indicateurs du tableau de bord (statistiques:index) pour une

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
- *classe* **MockStockConnector**(StockConnector) :17 — Données d'exemple, utilisées tant que l'accès au SQL Server du FRPS
- *classe* **SageSQLServerConnector**(StockConnector) :62 — Connexion en lecture seule au SQL Server du FRPS (Sage Gescom).
- `get_stock_connector()` :108

### `stock_sync/management/commands/sync_stock.py` (36 l.)
- *classe* **Command**(BaseCommand) :8

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

`templates/accounts/login.html`, `templates/base.html`, `templates/catalogue/importer.html`, `templates/catalogue/liste.html`, `templates/commandes/detail.html`, `templates/commandes/historique.html`, `templates/commandes/panier.html`, `templates/notifications/liste.html`, `templates/paiements/gerer.html`, `templates/paiements/modifier.html`, `templates/paiements/payer.html`, `templates/paiements/succes.html`, `templates/pwa/hors_ligne.html`, `templates/pwa/manifest.webmanifest`, `templates/pwa/sw.js`, `templates/statistiques/index.html`, `templates/statistiques/par_district.html`, `templates/statistiques/par_fosa.html`, `templates/statistiques/par_produit.html`, `templates/statistiques/stock.html`

