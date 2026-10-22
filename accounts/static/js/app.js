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
                afficherErreur(fiche, "Connexion interrompue. Réessayez.");
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
