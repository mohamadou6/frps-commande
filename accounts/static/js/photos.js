// Photos jointes aux réclamations : réduites sur le téléphone avant l'envoi.
// Une photo de téléphone pèse 3 à 5 Mo, soit plusieurs minutes sur le réseau d'une
// FOSA ; réduite à 1600 px en JPEG, elle passe sous 300 Ko. Le serveur réduit de
// toute façon (reclamations/services.py preparer_photo) : si ce script échoue ou que
// le navigateur est trop ancien, le formulaire part avec les originaux.
(function () {
    "use strict";
    var COTE_MAX = 1600;
    var QUALITE = 0.8;
    var SEUIL_OCTETS = 300 * 1024;

    function avertir(texte) {
        if (window.frpsToast) window.frpsToast(texte, "warning");
        else window.alert(texte);
    }

    function reduire(fichier) {
        if (fichier.size <= SEUIL_OCTETS && fichier.type === "image/jpeg") return Promise.resolve(fichier);
        return new Promise(function (resoudre) {
            var url = URL.createObjectURL(fichier);
            var image = new Image();
            image.onload = function () {
                // Le navigateur applique l'orientation EXIF en dessinant l'image.
                var echelle = Math.min(1, COTE_MAX / Math.max(image.naturalWidth, image.naturalHeight));
                var toile = document.createElement("canvas");
                toile.width = Math.round(image.naturalWidth * echelle);
                toile.height = Math.round(image.naturalHeight * echelle);
                var ctx = toile.getContext("2d");
                ctx.fillStyle = "#fff"; // fond blanc sous un PNG transparent
                ctx.fillRect(0, 0, toile.width, toile.height);
                ctx.drawImage(image, 0, 0, toile.width, toile.height);
                URL.revokeObjectURL(url);
                toile.toBlob(function (blob) {
                    if (!blob || blob.size >= fichier.size) return resoudre(fichier);
                    var nom = fichier.name.replace(/\.[^.]*$/, "") + ".jpg";
                    resoudre(new File([blob], nom, {type: "image/jpeg"}));
                }, "image/jpeg", QUALITE);
            };
            // Format que le navigateur ne sait pas afficher (HEIC sur certains
            // téléphones) : on l'envoie tel quel, le serveur dira s'il le lit.
            image.onerror = function () { URL.revokeObjectURL(url); resoudre(fichier); };
            image.src = url;
        });
    }

    function afficherVignettes(zone, fichiers) {
        zone.textContent = "";
        fichiers.forEach(function (fichier) {
            var vignette = document.createElement("img");
            vignette.alt = fichier.name;
            vignette.src = URL.createObjectURL(fichier);
            vignette.onload = function () { URL.revokeObjectURL(vignette.src); };
            zone.appendChild(vignette);
        });
    }

    function brancher(champ) {
        var max = parseInt(champ.getAttribute("data-photos-max"), 10) || 3;
        var formulaire = champ.form;
        var zone = champ.parentNode.querySelector("[data-photos-apercu]");
        var boutons = formulaire ? formulaire.querySelectorAll("button[type=submit]") : [];
        var enCours = null;

        function bloquer(etat) {
            Array.prototype.forEach.call(boutons, function (bouton) { bouton.disabled = etat; });
        }

        champ.addEventListener("change", function () {
            var fichiers = Array.prototype.slice.call(champ.files || []);
            if (fichiers.length > max) {
                avertir(max + " photos au maximum. Choisissez-en moins.");
                champ.value = "";
                if (zone) zone.textContent = "";
                return;
            }
            if (zone) afficherVignettes(zone, fichiers);
            if (!fichiers.length || typeof DataTransfer === "undefined") return;

            bloquer(true);
            enCours = Promise.all(fichiers.map(reduire)).then(function (reduits) {
                try {
                    var transfert = new DataTransfer();
                    reduits.forEach(function (f) { transfert.items.add(f); });
                    champ.files = transfert.files;
                } catch (e) { /* navigateur qui refuse : les originaux partent */ }
            }).catch(function () { /* idem */ }).then(function () {
                enCours = null;
                bloquer(false);
            });
        });

        if (formulaire) {
            formulaire.addEventListener("submit", function (evenement) {
                if (!enCours) return;
                evenement.preventDefault();
                enCours.then(function () { formulaire.requestSubmit ? formulaire.requestSubmit() : formulaire.submit(); });
            });
        }
    }

    document.querySelectorAll("input[data-photos]").forEach(brancher);
})();
