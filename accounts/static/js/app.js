// Comportements communs de l'application FRPS. Fichier statique : téléchargé une
// fois puis servi par le cache du service worker, au lieu d'être recopié dans
// chaque page. Chaque bloc vérifie que sa page le concerne avant d'agir.
(function () {
    "use strict";

    var mouvementReduit = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

    // ---------- Barre de chargement ----------
    // Sur le réseau lent des FOSA, un toucher restait plusieurs secondes sans réponse
    // visible et la FOSA retouchait le lien. La barre démarre au clic et la page
    // suivante la remplace.
    var barre = document.querySelector(".barre-chargement");
    var minuteurBarre = null;

    function demarrerChargement() {
        if (!barre) return;
        barre.className = "barre-chargement";
        void barre.offsetWidth; // repart de zéro si elle était déjà lancée
        barre.className = "barre-chargement en-cours";
        clearTimeout(minuteurBarre);
        // Téléchargement non repéré ou réponse qui ne change pas de page : on la
        // retire au bout d'un moment plutôt que de la laisser figée.
        minuteurBarre = setTimeout(arreterChargement, 15000);
    }

    function arreterChargement() {
        if (!barre) return;
        clearTimeout(minuteurBarre);
        if (barre.classList.contains("en-cours")) barre.className = "barre-chargement fini";
    }

    window.frpsChargement = demarrerChargement;

    // Retour arrière : le navigateur peut ressortir la page telle qu'on l'a quittée,
    // barre comprise.
    window.addEventListener("pageshow", function () {
        if (barre) barre.className = "barre-chargement";
    });

    // Téléchargements (PDF, reçus, exports Excel) : la page ne change pas.
    var TELECHARGEMENT = /\/(document|document-staff|telecharger|telecharger-staff|pdf|recu|recu-staff)\//;

    // Écouteurs posés sur window : ils passent après ceux de la page et de Bootstrap,
    // et voient donc si le clic ou l'envoi a été annulé (menu déroulant, confirmation
    // refusée, ajout au panier sans rechargement).
    window.addEventListener("click", function (evenement) {
        if (evenement.defaultPrevented || evenement.button !== 0) return;
        if (evenement.metaKey || evenement.ctrlKey || evenement.shiftKey || evenement.altKey) return;
        var lien = evenement.target.closest ? evenement.target.closest("a[href]") : null;
        if (!lien) return;
        if (lien.target && lien.target !== "_self") return;
        if (lien.hasAttribute("download") || lien.getAttribute("href").charAt(0) === "#") return;
        var url = new URL(lien.href, window.location.href);
        if (url.origin !== window.location.origin) return;
        if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return;
        if (TELECHARGEMENT.test(url.pathname) || url.searchParams.has("export")) return;
        demarrerChargement();
    });

    window.addEventListener("submit", function (evenement) {
        if (evenement.defaultPrevented) return;
        var formulaire = evenement.target;
        if (formulaire.target && formulaire.target !== "_self") return;
        if (evenement.submitter && evenement.submitter.name === "export") return;
        demarrerChargement();
    });

    // ---------- Messages qui glissent (toasts) ----------
    var zoneToasts = document.querySelector(".zone-toasts");
    var ICONES = {success: "✅", info: "ℹ️", warning: "⚠️", danger: "⛔"};

    function retirerToast(toast) {
        if (toast.classList.contains("sortie")) return;
        toast.classList.add("sortie");
        setTimeout(function () { if (toast.parentNode) toast.parentNode.removeChild(toast); }, mouvementReduit ? 0 : 260);
    }

    function brancherToast(toast, rang) {
        var fermer = toast.querySelector(".toast-fermer");
        if (fermer) fermer.addEventListener("click", function () { retirerToast(toast); });
        var niveau = toast.getAttribute("data-niveau");
        // Erreurs et avertissements restent jusqu'à ce qu'on les ferme : ils
        // demandent souvent une action (quantité refusée, stock insuffisant…).
        if (niveau === "danger" || niveau === "warning") return;
        var duree = Math.min(12000, 4500 + toast.textContent.length * 45) + (rang || 0) * 300;
        var minuteur = setTimeout(function () { retirerToast(toast); }, duree);
        // Un doigt posé dessus : la FOSA est en train de lire, on ne l'efface pas.
        toast.addEventListener("pointerdown", function () { clearTimeout(minuteur); });
    }

    function afficherToast(texte, niveau) {
        if (!zoneToasts || !texte) return;
        niveau = ICONES[niveau] ? niveau : "success";
        var toast = document.createElement("div");
        toast.className = "toast-msg";
        toast.setAttribute("data-niveau", niveau);
        if (niveau === "danger") toast.setAttribute("role", "alert");
        var icone = document.createElement("span");
        icone.className = "toast-icone";
        icone.setAttribute("aria-hidden", "true");
        icone.textContent = ICONES[niveau];
        var corps = document.createElement("span");
        corps.className = "toast-texte";
        corps.textContent = texte;
        var fermer = document.createElement("button");
        fermer.type = "button";
        fermer.className = "toast-fermer";
        fermer.setAttribute("aria-label", "Fermer");
        fermer.textContent = "×";
        toast.appendChild(icone);
        toast.appendChild(corps);
        toast.appendChild(fermer);
        zoneToasts.appendChild(toast);
        brancherToast(toast, 0);
        // Ajouts en série au catalogue : pas plus de trois messages empilés.
        var visibles = zoneToasts.querySelectorAll(".toast-msg:not(.sortie)");
        if (visibles.length > 3) retirerToast(visibles[0]);
    }

    window.frpsToast = afficherToast;

    // Commande préparée hors connexion (bloc plus bas) : renseigné seulement si le
    // téléphone sait garder une commande (compte FOSA, IndexedDB disponible).
    var commandeHorsLigne = null;

    // ---------- Envoi sans réseau ----------
    // Un formulaire envoyé sans réseau menait à une page d'erreur du navigateur,
    // puis à « Pas de connexion », et la saisie était perdue. Quand le téléphone se
    // sait hors ligne, on bloque l'envoi sur place : la page et ses saisies restent.
    // Écoute en phase de capture, pour passer avant l'ajout au panier sans
    // rechargement et la barre de chargement.
    window.addEventListener("submit", function (evenement) {
        if (navigator.onLine !== false) return;
        var formulaire = evenement.target;
        if ((formulaire.getAttribute("method") || "get").toLowerCase() !== "post") return;
        // L'ajout au panier du catalogue, lui, part dans la commande hors connexion.
        if (commandeHorsLigne && formulaire.classList.contains("form-ajout")) return;
        evenement.preventDefault();
        evenement.stopImmediatePropagation();
        afficherToast("Pas de réseau : rien n'a été envoyé. Vos saisies sont conservées, réessayez quand le réseau revient.", "warning");
    }, true);

    // ---------- Bandeau hors connexion ----------
    // Le service worker marque <html data-hors-ligne="1"> quand il ressert une page
    // enregistrée (réseau absent ou trop lent) : sans ce bandeau, rien ne la
    // distinguait d'une page à jour, stock compris.
    (function () {
        var bandeau = document.getElementById("bandeau-hors-ligne");
        if (!bandeau) return;
        var texte = bandeau.querySelector("[data-hors-ligne-texte]");
        var actualiser = bandeau.querySelector("[data-hors-ligne-actualiser]");
        var racine = document.documentElement;
        var depuisCache = racine.getAttribute("data-hors-ligne") === "1";

        function dateEnregistrement() {
            var brut = racine.getAttribute("data-enregistre-le");
            var date = brut ? new Date(brut) : null;
            if (!date || isNaN(date.getTime())) return "";
            return " le " + date.toLocaleDateString("fr-FR", {day: "2-digit", month: "2-digit"}) +
                " à " + date.toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"});
        }

        function afficher() {
            var horsLigne = navigator.onLine === false;
            if (!horsLigne && !depuisCache) {
                bandeau.hidden = true;
                return;
            }
            var message = horsLigne ? "Pas de réseau. " : "Réseau lent ou coupé. ";
            message += depuisCache
                ? "Version enregistrée" + dateEnregistrement() + " : le stock et les prix ont pu changer."
                : "Les pages déjà ouvertes restent consultables ; rien ne sera envoyé avant le retour du réseau.";
            texte.textContent = message;
            actualiser.hidden = horsLigne || !depuisCache;
            bandeau.hidden = false;
        }

        actualiser.addEventListener("click", function () {
            demarrerChargement();
            window.location.reload();
        });
        window.addEventListener("online", afficher);
        window.addEventListener("offline", afficher);
        afficher();
    })();

    if (zoneToasts) {
        Array.prototype.forEach.call(zoneToasts.querySelectorAll(".toast-msg"), brancherToast);
    }

    // ---------- Panneau du menu (téléphone) ----------
    // Un toucher hors du panneau (sur le voile) le referme.
    var panneau = document.getElementById("navPrincipale");
    if (panneau) {
        document.addEventListener("click", function (evenement) {
            if (!panneau.classList.contains("show") || !window.bootstrap) return;
            if (panneau.contains(evenement.target)) return;
            if (evenement.target.closest && evenement.target.closest('[data-bs-target="#navPrincipale"]')) return;
            window.bootstrap.Collapse.getOrCreateInstance(panneau, {toggle: false}).hide();
        });
        document.addEventListener("keydown", function (evenement) {
            if (evenement.key === "Escape" && panneau.classList.contains("show") && window.bootstrap) {
                window.bootstrap.Collapse.getOrCreateInstance(panneau, {toggle: false}).hide();
            }
        });
    }

    // ---------- Barre du haut : ombre renforcée dès qu'on fait défiler (ordinateur) ----------
    if (document.querySelector(".app-navbar")) {
        var entetereduit = false;
        window.addEventListener("scroll", function () {
            var reduit = window.scrollY > 12;
            if (reduit !== entetereduit) {
                entetereduit = reduit;
                document.body.classList.toggle("entete-reduit", reduit);
            }
        }, {passive: true});
    }

    // ---------- Chiffres des encarts qui défilent jusqu'à leur valeur ----------
    // Seulement les encarts qui ne contiennent qu'un nombre (suivi de FCFA ou %).
    // Le texte d'origine est remis tel quel à la fin, au caractère près.
    if (!mouvementReduit && window.requestAnimationFrame) {
        Array.prototype.forEach.call(document.querySelectorAll(".border.rounded-3 .fw-bold"), function (element) {
            if (element.children.length) return;
            var original = element.textContent;
            var morceaux = original.trim().match(/^(\d[\d\s  ]*?)(,\d+)?(\s*(?:FCFA|%))?$/);
            if (!morceaux) return;
            var valeur = parseInt(morceaux[1].replace(/\D/g, ""), 10);
            if (!(valeur > 1)) return;
            var separateur = (morceaux[1].match(/\d([\s  ])\d/) || [])[1] || "";
            var suffixe = morceaux[3] || "";
            var debut = null;
            var DUREE = 900;

            function formater(nombre) {
                var texte = String(nombre);
                if (separateur) texte = texte.replace(/\B(?=(\d{3})+(?!\d))/g, separateur);
                return texte + suffixe;
            }

            function pas(instant) {
                if (debut === null) debut = instant;
                var avancement = Math.min(1, (instant - debut) / DUREE);
                var adouci = 1 - Math.pow(1 - avancement, 3);
                if (avancement < 1) {
                    element.textContent = formater(Math.round(valeur * adouci));
                    window.requestAnimationFrame(pas);
                } else {
                    element.textContent = original;
                }
            }

            element.textContent = formater(0);
            window.requestAnimationFrame(pas);
        });
    }

    // ---------- Catalogue : recherche instantanée ----------
    // Filtre les fiches déjà affichées pendant la frappe, sans recharger la page.
    // Mêmes règles que le serveur (catalogue/views.py, _mots_recherches et
    // _nom_contient) : accents et majuscules ignorés, chaque mot cherché à part,
    // espaces et ponctuation sans effet, « y » lu comme « i ». Toute modification de
    // ces règles se fait aux deux endroits.
    (function () {
        var champ = document.getElementById("champ-recherche");
        if (!champ || !String.prototype.normalize) return;
        // Pas de grille quand la page n'a trouvé aucun produit : toute nouvelle saisie
        // repart alors vers le serveur.
        var grille = document.querySelector(".catalogue-grille");
        var formulaire = champ.form;
        var compte = document.getElementById("compte-produits");
        var aucun = document.getElementById("aucun-resultat");

        var marques, lettres;
        try {
            marques = new RegExp("\\p{Mn}", "gu");
            lettres = new RegExp("[\\p{L}\\p{N}]+", "gu");
        } catch (e) {
            marques = /[̀-ͯ]/g;
            lettres = /[a-z0-9À-ɏ]+/g;
        }

        function mots(texte) {
            var simplifie = String(texte).trim().toLowerCase().normalize("NFD").replace(marques, "").replace(/y/g, "i");
            return simplifie.match(lettres) || [];
        }

        var fiches = !grille ? [] : Array.prototype.map.call(grille.children, function (colonne) {
            var nom = colonne.querySelector(".produit-nom");
            return {colonne: colonne, compact: mots(nom ? nom.textContent : "").join("")};
        });

        // La page peut déjà être le résultat d'une recherche du serveur : elle ne
        // contient alors que ces produits-là. On ne peut filtrer sur place que si la
        // nouvelle saisie affine l'ancienne ; sinon on redemande au serveur.
        var motsServeur = mots(champ.defaultValue);

        function affineLaRecherche(saisis) {
            return motsServeur.every(function (ancien) {
                return saisis.some(function (nouveau) { return nouveau.indexOf(ancien) !== -1; });
            });
        }

        function demanderAuServeur(saisis) {
            return !grille || (motsServeur.length && !affineLaRecherche(saisis));
        }

        function filtrer() {
            var texte = champ.value.trim();
            var saisis = mots(texte);
            var nombre = 0;
            fiches.forEach(function (fiche) {
                var garde = saisis.every(function (mot) { return fiche.compact.indexOf(mot) !== -1; });
                if (fiche.colonne.hidden === garde) fiche.colonne.hidden = !garde;
                if (garde) nombre++;
            });
            var s = nombre > 1 || nombre === 0 ? "s" : "";
            if (compte) {
                compte.textContent = nombre.toLocaleString("fr-FR") + " produit" + s + " disponible" + s
                    + (texte ? " pour « " + texte + " »" : "") + ".";
            }
            if (aucun) {
                aucun.hidden = nombre > 0;
                aucun.textContent = "Aucun produit ne correspond à « " + texte + " ».";
            }
            // L'adresse suit la saisie : un rechargement ou un retour arrière retrouve la
            // recherche. Les liens des rayons aussi : changer de rayon la conserve.
            try {
                var url = new URL(window.location.href);
                if (texte) url.searchParams.set("q", texte); else url.searchParams.delete("q");
                url.hash = "";
                window.history.replaceState(window.history.state, "", url.toString());
                Array.prototype.forEach.call(document.querySelectorAll(".rayon-lien"), function (lien) {
                    var cible = new URL(lien.href, window.location.href);
                    if (texte) cible.searchParams.set("q", texte); else cible.searchParams.delete("q");
                    lien.href = cible.pathname + cible.search;
                });
            } catch (e) { /* navigateur ancien : l'adresse ne suit pas, sans conséquence */ }
        }

        var minuteur = null;
        champ.addEventListener("input", function () {
            clearTimeout(minuteur);
            if (demanderAuServeur(mots(champ.value))) {
                // Laisse le temps de finir de taper avant de recharger.
                minuteur = setTimeout(function () { demarrerChargement(); formulaire.submit(); }, 900);
                return;
            }
            minuteur = setTimeout(filtrer, 90);
        });

        formulaire.addEventListener("submit", function (evenement) {
            if (demanderAuServeur(mots(champ.value))) return; // part au serveur
            evenement.preventDefault();
            clearTimeout(minuteur);
            filtrer();
            champ.blur(); // referme le clavier du téléphone
        });

        formulaire.classList.add("instantanee");

        // Ordinateur : « / » mène à la recherche, Échap l'efface.
        document.addEventListener("keydown", function (evenement) {
            if (evenement.key !== "/" || evenement.ctrlKey || evenement.metaKey || evenement.altKey) return;
            var actif = document.activeElement;
            if (actif && (actif.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(actif.tagName))) return;
            evenement.preventDefault();
            champ.focus();
            champ.select();
        });
        champ.addEventListener("keydown", function (evenement) {
            if (evenement.key !== "Escape" || !champ.value) return;
            champ.value = "";
            champ.dispatchEvent(new Event("input", {bubbles: true}));
        });
    })();

    // ---------- Commande préparée hors connexion ----------
    // Sans réseau, « Ajouter » au catalogue garde le produit sur le téléphone
    // (js/demandes.js). La FOSA envoie ensuite sa commande comme d'habitude : elle
    // part toute seule dès que le réseau revient (Background Sync, sinon à l'ouverture
    // d'une page ou au retour du réseau), et le serveur la valide à son arrivée avec le
    // stock et les prix de ce moment-là. Le panneau, dans base.html, montre à chaque
    // étape où en est la commande, puis ce qui a été demandé et servi.
    (function () {
        var conteneur = document.getElementById("commande-hors-ligne");
        var D = window.FrpsDemandes;
        if (!conteneur || !D || !D.disponible() || !window.Promise || !window.fetch) return;

        var compte = conteneur.getAttribute("data-compte");
        var urlEnvoi = conteneur.getAttribute("data-url-envoi");
        var syncPossible = !!(navigator.serviceWorker && window.SyncManager);
        var demandes = [];
        var envoiEnCours = false;
        var reseauInsuffisant = false; // dernier envoi coupé par le réseau
        var brouillonOuvert = false;
        // Un ajout en ligne coupé par le réseau alors que le téléphone se croit connecté
        // (réseau présent mais sans données, fréquent) : pendant une minute, le toucher
        // suivant garde le produit sur le téléphone au lieu d'échouer encore.
        var coupureLe = 0;
        var DUREE_COUPURE_MS = 60000;

        function jeton() {
            // Le cookie d'abord : Django change le jeton à chaque connexion, et une page
            // resservie depuis le cache porte celui de son enregistrement.
            var morceau = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
            return morceau ? decodeURIComponent(morceau[1]) : conteneur.getAttribute("data-jeton");
        }

        function brouillon() {
            return demandes.filter(function (d) { return d.etat === "brouillon"; })[0] || null;
        }

        function enAttente() {
            return demandes.filter(function (d) { return d.etat === "en_attente"; });
        }

        function nombre(valeur, decimales) {
            return Number(valeur).toLocaleString("fr-FR", {minimumFractionDigits: decimales, maximumFractionDigits: decimales});
        }

        function estimation(lignes) {
            var total = lignes.reduce(function (somme, l) { return somme + l.prix * l.quantite; }, 0);
            return nombre(Math.round(total), 0) + " FCFA";
        }

        function produits(n) {
            return n + " produit" + (n > 1 ? "s" : "");
        }

        function dateCourte(iso) {
            var date = iso ? new Date(iso) : null;
            if (!date || isNaN(date.getTime())) return "";
            return date.toLocaleDateString("fr-FR", {day: "2-digit", month: "2-digit"}) +
                " à " + date.toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"});
        }

        function el(balise, classe, texte) {
            var element = document.createElement(balise);
            if (classe) element.className = classe;
            if (texte !== undefined) element.textContent = texte;
            return element;
        }

        function bouton(texte, classe, action, uuid) {
            var b = el("button", "btn btn-sm " + classe, texte);
            b.type = "button";
            b.setAttribute("data-action", action);
            if (uuid) b.setAttribute("data-uuid", uuid);
            return b;
        }

        function tableau(entetes, rangees) {
            var enveloppe = el("div", "table-responsive my-2");
            var table = el("table", "table table-sm align-middle mb-0");
            var tete = el("tr");
            entetes.forEach(function (titre) { tete.appendChild(el("th", "", titre)); });
            table.appendChild(el("thead")).appendChild(tete);
            var corps = table.appendChild(el("tbody"));
            rangees.forEach(function (cellules) {
                var rangee = corps.appendChild(el("tr"));
                cellules.forEach(function (cellule) {
                    var td = rangee.appendChild(el("td"));
                    if (cellule && cellule.nodeType) td.appendChild(cellule);
                    else td.textContent = cellule;
                });
            });
            enveloppe.appendChild(table);
            return enveloppe;
        }

        function carteBrouillon(demande) {
            var carte = el("details", "app-carte hors-ligne-carte etat-brouillon");
            carte.open = brouillonOuvert;
            carte.addEventListener("toggle", function () { brouillonOuvert = carte.open; });
            var resume = carte.appendChild(el("summary"));
            resume.appendChild(el("span", "hors-ligne-titre", "📡 Commande préparée sur ce téléphone"));
            resume.appendChild(el("span", "hors-ligne-resume",
                produits(demande.lignes.length) + " · environ " + estimation(demande.lignes)));
            carte.appendChild(el("p", "small text-secondary mb-0",
                "Prix et stock du catalogue enregistré. Le FRPS les vérifie à l'arrivée de la commande " +
                "et ne facture que ce qu'il peut servir."));
            // Trois colonnes seulement (prix sous le nom) : tient sur un téléphone sans
            // faire défiler le tableau pour atteindre le bouton de retrait.
            carte.appendChild(tableau(["Produit", "Quantité", ""], demande.lignes.map(function (ligne) {
                var produit = el("div");
                produit.appendChild(el("div", "", ligne.nom));
                produit.appendChild(el("div", "small text-secondary", nombre(ligne.prix, 2) + " FCFA l'unité (indicatif)"));
                var champ = el("input", "form-control form-control-sm quantite-panier");
                champ.type = "number";
                champ.min = "0";
                if (ligne.stock) champ.max = String(ligne.stock);
                champ.value = String(ligne.quantite);
                champ.setAttribute("data-produit", ligne.produit);
                champ.setAttribute("aria-label", "Quantité pour " + ligne.nom);
                var retirer = bouton("✕", "btn-outline-danger", "retirer");
                retirer.setAttribute("data-produit", ligne.produit);
                retirer.setAttribute("aria-label", "Retirer " + ligne.nom);
                retirer.title = "Retirer";
                return [produit, champ, retirer];
            })));
            var actions = carte.appendChild(el("div", "d-flex flex-wrap gap-2 align-items-center"));
            actions.appendChild(bouton("Envoyer la commande", "btn-primary", "valider"));
            actions.appendChild(bouton("Vider", "btn-link text-secondary", "vider"));
            actions.appendChild(el("span", "small text-secondary",
                "Elle partira toute seule dès le retour du réseau."));
            return carte;
        }

        function carteEnAttente(demande) {
            var carte = el("div", "app-carte hors-ligne-carte etat-attente");
            carte.appendChild(el("div", "hors-ligne-titre", "📤 Commande en attente d'envoi"));
            carte.appendChild(el("div", "small", "Préparée le " + dateCourte(demande.validee_le || demande.creee_le) +
                " · " + produits(demande.lignes.length) + " · environ " + estimation(demande.lignes)));
            var etat;
            if (envoiEnCours) etat = "Envoi en cours…";
            else if (demande.blocage === "connexion") etat = "Votre session a expiré : reconnectez-vous, la commande partira ensuite.";
            else if (navigator.onLine === false) {
                etat = syncPossible
                    ? "Elle partira toute seule dès le retour du réseau, même application fermée."
                    : "Elle partira dès que l'application sera ouverte avec du réseau.";
            } else if (reseauInsuffisant || demande.blocage) etat = "Pas encore passée (réseau faible ou serveur occupé) : nouvel essai automatique.";
            else etat = "Elle part dès que le réseau le permet.";
            carte.appendChild(el("div", "small text-secondary mt-1", etat));
            var detail = carte.appendChild(el("details", "small mt-1"));
            detail.appendChild(el("summary", "", "Voir les produits"));
            var liste = detail.appendChild(el("ul", "mb-1"));
            demande.lignes.forEach(function (ligne) { liste.appendChild(el("li", "", ligne.nom + " × " + ligne.quantite)); });
            var actions = carte.appendChild(el("div", "d-flex flex-wrap gap-2 mt-2"));
            if (!envoiEnCours && navigator.onLine !== false) {
                actions.appendChild(bouton("Envoyer maintenant", "btn-primary", "envoyer"));
            }
            actions.appendChild(bouton("Annuler cette commande", "btn-link text-secondary", "annuler", demande.uuid));
            return carte;
        }

        function carteEnvoyee(demande) {
            var resultat = demande.resultat || {};
            var servie = resultat.statut !== "annulee";
            var carte = el("div", "app-carte hors-ligne-carte " + (servie ? "etat-envoyee" : "etat-refusee"));
            carte.appendChild(el("div", "hors-ligne-titre", servie
                ? "✅ Commande n° " + resultat.commande_id + " reçue et validée par le FRPS"
                : "⚠️ Commande reçue, mais rien n'a pu être servi : stock épuisé"));
            carte.appendChild(el("div", "small", "Envoyée le " + dateCourte(demande.envoyee_le) +
                (servie ? " · montant final : " + resultat.montant_total + " FCFA" : "")));

            // Ce qui a été servi en moins, et les produits retirés du catalogue entre-temps.
            var recues = {};
            (resultat.lignes || []).forEach(function (ligne) { recues[ligne.produit] = ligne; });
            var ecarts = [];
            demande.lignes.forEach(function (ligne) {
                var recue = recues[ligne.produit];
                if (!recue) ecarts.push([ligne.nom, String(ligne.quantite), "0 (plus au catalogue)"]);
                else if (recue.servie < recue.demandee) ecarts.push([recue.nom, String(recue.demandee), String(recue.servie)]);
            });
            if (ecarts.length && servie) {
                carte.appendChild(el("div", "small fw-semibold mt-2", "Servi en moins que demandé (stock du jour) :"));
                carte.appendChild(tableau(["Produit", "Demandé", "Servi"], ecarts));
            } else if (servie) {
                carte.appendChild(el("div", "small text-secondary mt-1", "Tout ce que vous aviez demandé a été servi."));
            }
            var actions = carte.appendChild(el("div", "d-flex flex-wrap gap-2 mt-2"));
            if (resultat.url_detail) {
                var lien = el("a", "btn btn-sm btn-outline-primary", "Voir la commande");
                lien.href = resultat.url_detail;
                actions.appendChild(lien);
            }
            actions.appendChild(bouton("OK", "btn-primary", "effacer", demande.uuid));
            return carte;
        }

        function carteRefusee(demande) {
            var carte = el("div", "app-carte hors-ligne-carte etat-refusee");
            carte.appendChild(el("div", "hors-ligne-titre", "⛔ Commande refusée par le serveur"));
            carte.appendChild(el("div", "small", (demande.message || "") + " Rien n'a été commandé."));
            var actions = carte.appendChild(el("div", "d-flex flex-wrap gap-2 mt-2"));
            actions.appendChild(bouton("OK", "btn-primary", "effacer", demande.uuid));
            return carte;
        }

        function afficher() {
            var cartes = [];
            demandes.forEach(function (d) { if (d.etat === "envoyee") cartes.push(carteEnvoyee(d)); });
            demandes.forEach(function (d) { if (d.etat === "refusee") cartes.push(carteRefusee(d)); });
            enAttente().forEach(function (d) { cartes.push(carteEnAttente(d)); });
            if (brouillon()) cartes.push(carteBrouillon(brouillon()));
            while (conteneur.firstChild) conteneur.removeChild(conteneur.firstChild);
            cartes.forEach(function (carte) { conteneur.appendChild(carte); });
            conteneur.hidden = !cartes.length;
        }

        // Repère sur les fiches du catalogue, comme « Déjà au panier ».
        function marquerFiches() {
            var quantites = {};
            var b = brouillon();
            if (b) b.lignes.forEach(function (l) { quantites[l.produit] = l.quantite; });
            Array.prototype.forEach.call(document.querySelectorAll(".form-ajout[data-produit-id]"), function (formulaire) {
                var fiche = formulaire.closest(".produit-card");
                if (!fiche) return;
                var repere = fiche.querySelector(".produit-hors-ligne");
                var quantite = quantites[formulaire.getAttribute("data-produit-id")];
                if (!quantite) {
                    if (repere) repere.parentNode.removeChild(repere);
                    return;
                }
                if (!repere) {
                    repere = el("div", "produit-au-panier produit-hors-ligne");
                    fiche.insertBefore(repere, formulaire);
                }
                repere.textContent = "📡 Commande hors connexion : " + quantite;
            });
        }

        function recharger() {
            return D.lister(compte).then(function (liste) {
                demandes = liste;
                afficher();
                marquerFiches();
                return liste;
            });
        }

        function erreurMemoire() {
            afficherToast("Impossible d'enregistrer sur ce téléphone (mémoire pleine ?). Rien n'a été gardé.", "danger");
        }

        function programmerSynchro() {
            if (!syncPossible) return;
            navigator.serviceWorker.ready.then(function (enregistrement) {
                return enregistrement.sync.register(D.ETIQUETTE_SYNC);
            }).catch(function () { /* refusé : la page enverra elle-même */ });
        }

        function envoyer() {
            if (envoiEnCours || navigator.onLine === false || !enAttente().length) return;
            envoiEnCours = true;
            afficher();
            D.envoyerEnAttente({url: urlEnvoi, jeton: jeton, compte: compte}).then(function (bilan) {
                envoiEnCours = false;
                reseauInsuffisant = bilan.reseau;
                if (bilan.envoyees || bilan.refusees) coupureLe = 0;
                // Le service worker est déjà en train d'envoyer : on relit un peu plus tard.
                if (bilan.occupe) setTimeout(recharger, 5000);
                return recharger().then(function () {
                    if (bilan.envoyees) {
                        afficherToast(bilan.envoyees > 1
                            ? bilan.envoyees + " commandes préparées hors connexion ont été reçues par le FRPS."
                            : "Votre commande préparée hors connexion a été reçue par le FRPS.", "success");
                    }
                    if (bilan.refusees) afficherToast("Une commande a été refusée par le serveur : détail en haut de la page.", "danger");
                });
            }, function () {
                envoiEnCours = false;
                afficher();
            });
        }

        function ajouter(formulaire) {
            var fiche = formulaire.closest(".produit-card");
            var champ = formulaire.querySelector('input[name="quantite"]');
            var boutonAjout = formulaire.querySelector("button");
            var quantite = parseInt(champ ? champ.value : "1", 10);
            var produit = {
                id: formulaire.getAttribute("data-produit-id"),
                nom: formulaire.getAttribute("data-produit-nom"),
                prix: formulaire.getAttribute("data-produit-prix"),
                stock: formulaire.getAttribute("data-produit-stock"),
            };
            if (!(quantite > 0)) {
                afficherToast("Quantité invalide.", "danger");
                return;
            }
            var erreur = fiche ? fiche.querySelector(".erreur-ajout") : null;
            if (erreur) erreur.hidden = true;
            var sansReseau = navigator.onLine === false || Date.now() - coupureLe < DUREE_COUPURE_MS;
            D.fixerQuantite(compte, produit, quantite).then(recharger).then(function () {
                afficherToast(sansReseau
                    ? "Sans réseau : " + produit.nom + " gardé dans la commande préparée sur ce téléphone."
                    : produit.nom + " ajouté à la commande préparée sur ce téléphone (à envoyer depuis le cadre en haut de page).", "info");
                if (boutonAjout) {
                    boutonAjout.textContent = "Gardé ✓";
                    setTimeout(function () { boutonAjout.textContent = "Ajouter"; }, 1500);
                }
            }, erreurMemoire);
        }

        conteneur.addEventListener("click", function (evenement) {
            var cible = evenement.target.closest ? evenement.target.closest("[data-action]") : null;
            if (!cible) return;
            var action = cible.getAttribute("data-action");
            var uuid = cible.getAttribute("data-uuid");
            var suite = null;
            if (action === "retirer") {
                suite = D.fixerQuantite(compte, {id: cible.getAttribute("data-produit")}, 0);
            } else if (action === "vider") {
                if (!window.confirm("Retirer tous les produits de la commande préparée sur ce téléphone ?")) return;
                suite = D.viderBrouillon(compte);
            } else if (action === "valider") {
                var b = brouillon();
                if (!b || !window.confirm("Envoyer cette commande de " + produits(b.lignes.length) + " ?\n\n" +
                    "Elle partira dès que le réseau le permet. Le FRPS la valide à son arrivée, avec le stock " +
                    "et les prix de ce moment-là : il ne sert et ne facture que ce qui est disponible.")) return;
                suite = D.validerBrouillon(compte).then(function () {
                    programmerSynchro();
                    if (navigator.onLine === false) {
                        afficherToast("Commande enregistrée sur ce téléphone : elle partira dès le retour du réseau.", "success");
                    }
                });
            } else if (action === "envoyer") {
                envoyer();
                return;
            } else if (action === "annuler") {
                if (!window.confirm("Annuler cette commande ? Elle ne sera pas envoyée.\n\n" +
                    "Si elle est déjà partie, elle apparaîtra quand même dans « Mes commandes ».")) return;
                suite = D.supprimer(uuid);
            } else if (action === "effacer") {
                suite = D.supprimer(uuid);
            }
            if (suite) {
                suite.then(recharger).then(function () {
                    if (action === "valider" && navigator.onLine !== false) envoyer();
                }, erreurMemoire);
            }
        });

        // Correction d'une quantité dans le brouillon.
        conteneur.addEventListener("change", function (evenement) {
            var champ = evenement.target;
            if (!champ.matches || !champ.matches("input[data-produit]")) return;
            var quantite = parseInt(champ.value, 10) || 0;
            var max = parseInt(champ.max, 10);
            if (max && quantite > max) {
                quantite = max;
                afficherToast("Quantité ramenée au stock affiché (" + max + ").", "warning");
            }
            D.fixerQuantite(compte, {id: champ.getAttribute("data-produit")}, quantite).then(recharger, erreurMemoire);
        });

        commandeHorsLigne = {
            // Le produit va dans la commande hors connexion : sans réseau, juste après une
            // coupure, ou si une commande y est déjà commencée (on ne la coupe pas en deux).
            prendLaMain: function () {
                return navigator.onLine === false || !!brouillon() || Date.now() - coupureLe < DUREE_COUPURE_MS;
            },
            ajouter: ajouter,
            signalerCoupure: function () { coupureLe = Date.now(); },
        };

        // Envoi par la page : à l'ouverture, au retour du réseau, au retour sur
        // l'application, et toutes les minutes tant qu'une commande attend (réseau
        // présent mais trop faible pour qu'elle soit passée).
        recharger().then(function () {
            if (enAttente().length) {
                programmerSynchro();
                if (navigator.onLine !== false) envoyer();
            }
        }, function () { /* base illisible : le panneau reste masqué */ });
        window.addEventListener("online", function () {
            coupureLe = 0;
            afficher();
            envoyer();
        });
        window.addEventListener("offline", afficher);
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "visible") recharger().then(envoyer);
        });
        setInterval(function () {
            if (document.visibilityState === "visible" && navigator.onLine !== false) envoyer();
        }, 60000);
        // Envoi fait par le service worker (Background Sync) pendant que la page est ouverte.
        if (navigator.serviceWorker) {
            navigator.serviceWorker.addEventListener("message", function (evenement) {
                if (evenement.data === "demandes-mises-a-jour") recharger();
            });
        }
    })();

    // ---------- Catalogue : ajout au panier sans recharger la page ----------
    // Recharger les 1 200 fiches à chaque produit faisait perdre le rayon, la
    // recherche et la position. Si ce script n'est pas chargé, le formulaire part
    // normalement et le serveur ramène sur la même fiche.
    (function () {
        if (!document.querySelector("[data-ajout-instantane]") || !window.fetch || !window.FormData) return;
        var DELAI_MS = 20000;

        function mettreAJourPanier(donnees) {
            var bandeau = document.getElementById("bandeau-panier");
            if (bandeau) {
                bandeau.querySelector('[data-panier="nb"]').textContent = donnees.panier_nb;
                bandeau.querySelector('[data-panier="libelle"]').textContent = donnees.panier_nb > 1 ? "produits" : "produit";
                bandeau.querySelector('[data-panier="montant"]').textContent = donnees.panier_montant;
                bandeau.hidden = donnees.panier_montant_nul;
            }
            // Compteur du menu du haut et de l'onglet Panier du bas.
            Array.prototype.forEach.call(document.querySelectorAll("[data-badge-panier]"), function (badge) {
                badge.textContent = donnees.panier_nb;
                badge.hidden = !donnees.panier_nb;
            });
        }

        function marquerFiche(fiche, formulaire, quantite) {
            fiche.classList.add("au-panier");
            var repere = fiche.querySelector(".produit-au-panier");
            if (!repere) {
                repere = document.createElement("div");
                repere.className = "produit-au-panier";
                fiche.insertBefore(repere, formulaire);
            }
            repere.textContent = "🛒 Déjà au panier : " + quantite;
        }

        function afficherErreur(fiche, texte) {
            var zone = fiche.querySelector(".erreur-ajout");
            if (!zone) {
                if (!texte) return;
                zone = document.createElement("div");
                zone.className = "erreur-ajout text-danger small";
                fiche.appendChild(zone);
            }
            zone.textContent = texte;
            zone.hidden = !texte;
        }

        document.addEventListener("submit", function (evenement) {
            var formulaire = evenement.target;
            if (!formulaire.classList || !formulaire.classList.contains("form-ajout")) return;
            evenement.preventDefault();
            if (commandeHorsLigne && commandeHorsLigne.prendLaMain()) {
                commandeHorsLigne.ajouter(formulaire);
                return;
            }

            var fiche = formulaire.closest(".produit-card");
            var bouton = formulaire.querySelector("button");
            var corps = new FormData(formulaire);
            var arret = window.AbortController ? new AbortController() : null;
            var minuteur = arret ? setTimeout(function () { arret.abort(); }, DELAI_MS) : null;
            bouton.disabled = true;
            bouton.textContent = "Ajout…";
            afficherErreur(fiche, "");

            fetch(formulaire.action, {
                method: "POST",
                body: corps,
                credentials: "same-origin",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                signal: arret ? arret.signal : undefined,
            }).then(function (reponse) {
                var type = reponse.headers.get("Content-Type") || "";
                if (type.indexOf("application/json") === -1) {
                    // Session expirée ou erreur du serveur : on repasse par le parcours classique.
                    demarrerChargement();
                    formulaire.submit();
                    return null;
                }
                return reponse.json();
            }).then(function (donnees) {
                if (!donnees) return;
                bouton.disabled = false;
                if (!donnees.ok) {
                    bouton.textContent = "Ajouter";
                    afficherErreur(fiche, donnees.message);
                    afficherToast(donnees.message, "danger");
                    return;
                }
                marquerFiche(fiche, formulaire, donnees.quantite);
                mettreAJourPanier(donnees);
                afficherToast(donnees.message, "success");
                bouton.textContent = "Ajouté ✓";
                setTimeout(function () { bouton.textContent = "Ajouter"; }, 1500);
            }).catch(function () {
                bouton.disabled = false;
                bouton.textContent = "Ajouter";
                if (commandeHorsLigne) {
                    // Pas d'ajout automatique sur le téléphone : après un délai dépassé, le
                    // serveur a pu recevoir l'ajout malgré tout, et le produit serait compté
                    // deux fois. La FOSA décide en touchant à nouveau.
                    commandeHorsLigne.signalerCoupure();
                    afficherErreur(fiche, "Connexion interrompue : produit non ajouté. Touchez « Ajouter » à nouveau " +
                        "pour le garder dans une commande préparée sur ce téléphone.");
                } else {
                    afficherErreur(fiche, "Connexion interrompue : produit non ajouté. Réessayez.");
                }
            }).then(function () {
                if (minuteur) clearTimeout(minuteur);
            });
        });
    })();

    // ---------- Bandeau d'installation de l'application ----------
    // Affiché seulement si l'application n'est pas déjà installée et que
    // l'utilisateur ne l'a pas écarté. L'invitation de Chrome est captée dans le
    // <head> de base.html (window.__inviteInstallation), sinon elle serait perdue.
    (function () {
        var bandeau = document.getElementById("bandeau-installation");
        if (!bandeau) return;
        var texte = document.getElementById("texte-installation");
        var boutonInstaller = document.getElementById("bouton-installer");
        var boutonIgnorer = document.getElementById("bouton-ignorer-installation");
        var CLE_REFUS = "frps-installation-ecartee";

        function memoire(cle, valeur) {
            // localStorage lève une exception en navigation privée sur certains mobiles.
            try {
                if (valeur === undefined) return window.localStorage.getItem(cle);
                window.localStorage.setItem(cle, valeur);
            } catch (e) { return null; }
        }

        var dejaInstallee = window.matchMedia("(display-mode: standalone)").matches
            || navigator.standalone === true;
        if (dejaInstallee || memoire(CLE_REFUS) === "1") return;

        function afficher() { bandeau.hidden = false; }

        boutonIgnorer.addEventListener("click", function () {
            memoire(CLE_REFUS, "1");
            bandeau.hidden = true;
        });

        window.addEventListener("appinstalled", function () {
            memoire(CLE_REFUS, "1");
            bandeau.hidden = true;
        });

        if (/iphone|ipad|ipod/i.test(navigator.userAgent)) {
            // Safari n'expose aucune invitation programmable : on décrit le geste.
            texte.textContent = "Pour installer l'application : touchez le bouton Partager, puis « Sur l'écran d'accueil ».";
            boutonInstaller.hidden = true;
            afficher();
            return;
        }

        // Le texte du gabarit parle du téléphone, majoritaire chez les FOSA.
        var surMobile = window.matchMedia("(pointer: coarse)").matches
            || /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent);
        if (!surMobile) {
            texte.textContent = "Installez l'application sur cet ordinateur : elle s'ouvre "
                + "plus vite et reste consultable même sans connexion.";
        }

        boutonInstaller.addEventListener("click", function () {
            var invite = window.__inviteInstallation;
            if (!invite) return;
            invite.prompt();
            invite.userChoice.then(function () {
                window.__inviteInstallation = null;
                bandeau.hidden = true;
            });
        });

        if (window.__inviteInstallation) afficher();
        document.addEventListener("frps:installable", afficher);
    })();
})();

// Partage d'un PDF de commande vers WhatsApp (boutons des pages de commande).
// Global : appelé depuis l'attribut onclick des boutons. Écrit sans async/await
// pour qu'un navigateur ancien ne rejette pas tout ce fichier.
function partagerPdfWhatsApp(url, filename, texte, btn) {
    var libelleInitial = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; btn.textContent = "Préparation..."; }
    function terminer() {
        if (btn) { btn.disabled = false; btn.textContent = libelleInitial; }
    }
    return fetch(url, {credentials: "same-origin"}).then(function (reponse) {
        if (!reponse.ok) throw new Error("Téléchargement du PDF impossible");
        return reponse.blob();
    }).then(function (blob) {
        var fichier = new File([blob], filename, {type: "application/pdf"});
        if (navigator.canShare && navigator.canShare({files: [fichier]})) {
            return navigator.share({files: [fichier], title: filename, text: texte});
        }
        // Partage de fichiers non pris en charge (ex : ordinateur) : on télécharge le
        // PDF et on ouvre WhatsApp avec un message pré-rempli, à l'utilisateur d'y
        // joindre le fichier téléchargé.
        var lienTelechargement = document.createElement("a");
        lienTelechargement.href = window.URL.createObjectURL(blob);
        lienTelechargement.download = filename;
        lienTelechargement.click();
        window.open("https://wa.me/?text=" + encodeURIComponent(texte + " (voir le PDF téléchargé)"), "_blank");
    }).catch(function (e) {
        if (e && e.name !== "AbortError") {
            alert("Le partage a échoué : " + e.message);
        }
    }).then(terminer);
}
