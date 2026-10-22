// Commandes préparées hors connexion : stockage sur le téléphone et envoi au serveur.
//
// Chargé par les pages (base.html, avant js/app.js) ET par le service worker
// (importScripts dans templates/pwa/sw.js) : le service worker doit pouvoir envoyer
// les demandes en arrière-plan (Background Sync), page fermée. D'où IndexedDB plutôt
// que localStorage, inaccessible au service worker. Aucun accès au DOM ici.
//
// Une demande passe par ces états :
//   brouillon  -> la FOSA ajoute des produits (un seul brouillon par compte) ;
//   en_attente -> elle a touché « Envoyer » : la demande partira dès que possible ;
//   envoyee    -> le serveur l'a reçue et validée, `resultat` porte sa réponse ;
//   refusee    -> le serveur l'a refusée pour de bon, `message` dit pourquoi.
// Le serveur ne reprend que les produits et les quantités : stock et prix sont
// décidés à l'arrivée (commandes/services.py, valider_demande).
//
// Écrit sans async/await, comme js/app.js, pour qu'un navigateur ancien ne rejette
// pas le fichier entier.
(function (global) {
    "use strict";

    var NOM_BASE = "frps-hors-ligne";
    var MAGASIN = "demandes";
    var ETIQUETTE_SYNC = "frps-demandes";
    var VERROU_ENVOI = "frps-envoi-demandes";
    // Réseau lent : une demande est petite, mais la réponse peut mettre longtemps.
    var DELAI_ENVOI_MS = 60000;

    function disponible() {
        try {
            return !!global.indexedDB;
        } catch (e) {
            return false; // accès refusé (certains modes privés)
        }
    }

    var baseOuverte = null;

    function ouvrir() {
        if (baseOuverte) return baseOuverte;
        baseOuverte = new Promise(function (resoudre, rejeter) {
            var requete = global.indexedDB.open(NOM_BASE, 1);
            requete.onupgradeneeded = function () {
                var magasin = requete.result.createObjectStore(MAGASIN, {keyPath: "uuid"});
                magasin.createIndex("compte", "compte");
            };
            requete.onsuccess = function () {
                var base = requete.result;
                // Une autre version du fichier (mise à jour de l'app) demande la base :
                // on la libère, elle sera rouverte au prochain accès.
                base.onversionchange = function () {
                    base.close();
                    baseOuverte = null;
                };
                resoudre(base);
            };
            requete.onerror = function () {
                baseOuverte = null;
                rejeter(requete.error);
            };
        });
        return baseOuverte;
    }

    // Exécute `travail(magasin)` dans une transaction et résout avec sa valeur une fois
    // la transaction terminée (donc réellement écrite sur le téléphone).
    function transaction(mode, travail) {
        return ouvrir().then(function (base) {
            return new Promise(function (resoudre, rejeter) {
                var tx = base.transaction(MAGASIN, mode);
                var resultat;
                tx.oncomplete = function () { resoudre(resultat); };
                tx.onerror = function () { rejeter(tx.error); };
                tx.onabort = function () { rejeter(tx.error); };
                resultat = travail(tx.objectStore(MAGASIN));
            });
        });
    }

    function lireTout(magasin, compte, rappel) {
        var requete = compte === undefined ? magasin.getAll() : magasin.index("compte").getAll(String(compte));
        requete.onsuccess = function () { rappel(requete.result || []); };
    }

    function lister(compte) {
        var demandes = [];
        return transaction("readonly", function (magasin) {
            lireTout(magasin, compte, function (liste) { demandes = liste; });
        }).then(function () {
            return demandes.sort(function (a, b) { return (a.creee_le || "").localeCompare(b.creee_le || ""); });
        });
    }

    function nouvelUuid() {
        if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
        var octets = new Uint8Array(16);
        global.crypto.getRandomValues(octets);
        octets[6] = (octets[6] & 0x0f) | 0x40; // version 4
        octets[8] = (octets[8] & 0x3f) | 0x80; // variante RFC 4122
        var hexa = Array.prototype.map.call(octets, function (o) { return (o + 0x100).toString(16).slice(1); }).join("");
        return hexa.slice(0, 8) + "-" + hexa.slice(8, 12) + "-" + hexa.slice(12, 16) + "-" + hexa.slice(16, 20) + "-" + hexa.slice(20);
    }

    function maintenant() {
        return new Date().toISOString();
    }

    // Lit le brouillon du compte, le passe à `modifier`, et l'enregistre — le tout dans
    // une seule transaction, pour que deux ajouts rapprochés ne s'écrasent pas.
    function modifierBrouillon(compte, modifier) {
        var brouillon = null;
        return transaction("readwrite", function (magasin) {
            lireTout(magasin, compte, function (liste) {
                brouillon = liste.filter(function (d) { return d.etat === "brouillon"; })[0] || {
                    uuid: nouvelUuid(),
                    compte: String(compte),
                    etat: "brouillon",
                    lignes: [],
                    creee_le: maintenant(),
                };
                modifier(brouillon);
                if (brouillon.lignes.length) magasin.put(brouillon);
                else magasin.delete(brouillon.uuid);
            });
        }).then(function () { return brouillon; });
    }

    // Même règle que le panier en ligne (services.ajouter_produit) : la quantité saisie
    // remplace celle déjà présente, elle ne s'y ajoute pas. 0 retire le produit.
    function fixerQuantite(compte, produit, quantite) {
        return modifierBrouillon(compte, function (brouillon) {
            var id = Number(produit.id);
            var existante = brouillon.lignes.filter(function (l) { return l.produit === id; })[0];
            if (quantite <= 0) {
                brouillon.lignes = brouillon.lignes.filter(function (l) { return l.produit !== id; });
                return;
            }
            if (existante) {
                existante.quantite = quantite;
                return;
            }
            brouillon.lignes.push({
                produit: id,
                nom: produit.nom,
                // Prix et stock du catalogue enregistré : indicatifs seulement.
                prix: Number(produit.prix) || 0,
                stock: Number(produit.stock) || 0,
                quantite: quantite,
            });
        });
    }

    function viderBrouillon(compte) {
        return modifierBrouillon(compte, function (brouillon) { brouillon.lignes = []; });
    }

    // La FOSA a touché « Envoyer » : le brouillon devient une demande à envoyer.
    function validerBrouillon(compte) {
        return modifierBrouillon(compte, function (brouillon) {
            if (!brouillon.lignes.length) return;
            brouillon.etat = "en_attente";
            brouillon.validee_le = maintenant();
        });
    }

    function supprimer(uuid) {
        return transaction("readwrite", function (magasin) { magasin.delete(uuid); });
    }

    function enregistrer(demande) {
        return transaction("readwrite", function (magasin) { magasin.put(demande); });
    }

    function avecDelai(promesse, delai, arret) {
        return new Promise(function (resoudre, rejeter) {
            var minuteur = setTimeout(function () {
                if (arret) arret.abort();
                rejeter(new Error("delai depasse"));
            }, delai);
            promesse.then(function (valeur) {
                clearTimeout(minuteur);
                resoudre(valeur);
            }, function (erreur) {
                clearTimeout(minuteur);
                rejeter(erreur);
            });
        });
    }

    // Envoie une demande et range la réponse. Résout avec "envoyee", "refusee",
    // "garder" (à renvoyer plus tard : session, autre compte, serveur indisponible),
    // ou rejette si le réseau a manqué.
    function envoyerUne(demande, options) {
        var arret = global.AbortController ? new global.AbortController() : null;
        return Promise.resolve(options.jeton()).then(function (jeton) {
            return avecDelai(global.fetch(options.url, {
                method: "POST",
                credentials: "same-origin",
                headers: {"Content-Type": "application/json", "X-CSRFToken": jeton || ""},
                body: JSON.stringify({
                    uuid: demande.uuid,
                    compte: demande.compte,
                    lignes: demande.lignes.map(function (l) { return {produit: l.produit, quantite: l.quantite}; }),
                }),
                signal: arret ? arret.signal : undefined,
            }), DELAI_ENVOI_MS, arret);
        }).then(function (reponse) {
            var type = reponse.headers.get("Content-Type") || "";
            demande.tentatives = (demande.tentatives || 0) + 1;
            demande.derniere_tentative = maintenant();
            if (type.indexOf("application/json") === -1) {
                // Page de connexion (session expirée), refus CSRF ou erreur du serveur :
                // la demande n'a pas été traitée, on la garde.
                demande.blocage = reponse.redirected && /\/login\//.test(reponse.url) ? "connexion" : "serveur";
                return enregistrer(demande).then(function () { return "garder"; });
            }
            return reponse.json().then(function (donnees) {
                if (reponse.ok && donnees.ok) {
                    demande.etat = "envoyee";
                    demande.envoyee_le = maintenant();
                    demande.resultat = donnees;
                    delete demande.blocage;
                    return enregistrer(demande).then(function () { return "envoyee"; });
                }
                if (reponse.status === 400) {
                    demande.etat = "refusee";
                    demande.message = donnees.message || "Demande refusée.";
                    delete demande.blocage;
                    return enregistrer(demande).then(function () { return "refusee"; });
                }
                demande.blocage = donnees.code === "autre_compte" ? "autre_compte" : "serveur";
                return enregistrer(demande).then(function () { return "garder"; });
            });
        });
    }

    function envoyerToutes(options) {
        var bilan = {envoyees: 0, refusees: 0, restantes: 0, reseau: false};
        return lister(options.compte).then(function (demandes) {
            var aEnvoyer = demandes.filter(function (d) { return d.etat === "en_attente"; });
            // Une par une : sur un réseau lent, des envois en parallèle se gênent, et
            // une coupure arrête tout de suite les suivantes au lieu de les faire échouer.
            return aEnvoyer.reduce(function (suite, demande) {
                return suite.then(function () {
                    if (bilan.reseau) {
                        bilan.restantes++;
                        return null;
                    }
                    return envoyerUne(demande, options).then(function (issue) {
                        if (issue === "envoyee") bilan.envoyees++;
                        else if (issue === "refusee") bilan.refusees++;
                        else bilan.restantes++;
                    }, function () {
                        bilan.reseau = true;
                        bilan.restantes++;
                    });
                });
            }, Promise.resolve());
        }).then(function () { return bilan; });
    }

    // Envoie toutes les demandes en attente (de `options.compte`, ou de tous les comptes
    // depuis le service worker : le serveur refuse alors en 409 celles d'un autre compte,
    // qui restent en attente). `options.url` : adresse de synchronisation ;
    // `options.jeton` : fonction qui rend le jeton CSRF (éventuellement en promesse).
    //
    // La page et le service worker peuvent envoyer en même temps au retour du réseau.
    // Le serveur ne crée jamais de doublon (même uuid), mais le verrou évite d'envoyer
    // deux fois pour rien sur un réseau qui se paie au mégaoctet.
    function envoyerEnAttente(options) {
        if (global.navigator && global.navigator.locks && global.navigator.locks.request) {
            return global.navigator.locks.request(VERROU_ENVOI, {ifAvailable: true}, function (verrou) {
                if (!verrou) return {envoyees: 0, refusees: 0, restantes: 0, reseau: false, occupe: true};
                return envoyerToutes(options);
            });
        }
        return envoyerToutes(options);
    }

    global.FrpsDemandes = {
        ETIQUETTE_SYNC: ETIQUETTE_SYNC,
        disponible: disponible,
        lister: lister,
        fixerQuantite: fixerQuantite,
        viderBrouillon: viderBrouillon,
        validerBrouillon: validerBrouillon,
        supprimer: supprimer,
        envoyerEnAttente: envoyerEnAttente,
    };
})(self);
