{% load static %}// Service worker de l'application FRPS Nord en Ligne.
// Rendu par Django (voir frps_project/pwa.py) : les URL ci-dessous sont donc les
// URL hachées réelles, et ce fichier change dès qu'un fichier statique change —
// ce qui suffit au navigateur pour détecter une mise à jour.

const VERSION = "v3";
const CACHE_COQUILLE = "frps-coquille-" + VERSION; // ressources fixes de l'app
const CACHE_PAGES = "frps-pages-" + VERSION; // pages HTML déjà consultées
const PAGE_HORS_LIGNE = "{% url 'hors_ligne' %}";
const PREFIXE_STATIC = "{% get_static_prefix %}";
const VAPID_PUBLIC_KEY = "{{ vapid_public_key }}";
const URL_ABONNEMENT_PUSH = "{% url 'notifications:abonnement_push' %}";
const CSRF_TOKEN = "{{ csrf_token }}";

// Réseau lent : au-delà de ce délai on sert la version en cache plutôt que de
// laisser la FOSA devant une page blanche.
const DELAI_RESEAU_MS = 6000;

const RESSOURCES_COQUILLE = [
    PAGE_HORS_LIGNE,
    "{% static 'vendor/bootstrap/bootstrap.min.css' %}",
    "{% static 'vendor/bootstrap/bootstrap.bundle.min.js' %}",
    "{% static 'img/favicon.svg' %}",
    "{% static 'img/icon-192.png' %}",
    "{% static 'img/icon-512.png' %}",
    "{% static 'statistiques/js/combobox.js' %}",
];

// Jamais interceptées :
// - l'admin Django ;
// - les pages d'authentification, dont le jeton CSRF doit toujours être frais (un 403
//   au premier login sur mobile a déjà été corrigé une fois par un `never_cache`, ne
//   pas le réintroduire par le cache) ;
// - les téléchargements (PDF de bon de commande). Un clic sur un lien de
//   téléchargement est une *navigation* : la faire passer par `respondWith()` casse
//   la gestion du `Content-Disposition: attachment` sur Android, et le PDF, généré à
//   la volée, dépasse volontiers le délai réseau.
const HORS_PERIMETRE = [
    /^\/admin\//,
    /^\/login\/?$/,
    /^\/logout\/?$/,
    /\/telecharger(-staff)?\/$/,
    /\/pdf\//,
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE_COQUILLE)
            .then((cache) => cache.addAll(RESSOURCES_COQUILLE))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        (async () => {
            const noms = await caches.keys();
            await Promise.all(
                noms
                    .filter((nom) => nom !== CACHE_COQUILLE && nom !== CACHE_PAGES)
                    .map((nom) => caches.delete(nom))
            );
            await self.clients.claim();
        })()
    );
});

// Envoyé par la page de connexion : les pages en cache contiennent les données
// d'une FOSA, on les purge dès qu'il n'y a plus de session ouverte.
self.addEventListener("message", (event) => {
    if (event.data === "purge-pages") {
        event.waitUntil(caches.delete(CACHE_PAGES));
    }
});

// Le navigateur peut faire tourner le jeton d'abonnement push à tout moment
// (fréquent sur mobile), sans qu'aucune page ne soit ouverte pour le détecter
// via un rechargement classique : cet évènement est le seul moyen fiable de
// s'en réabonner et de renvoyer le nouvel abonnement au serveur automatiquement,
// desktop et mobile inclus.
function urlBase64ToUint8Array(base64) {
    const padding = "=".repeat((4 - (base64.length % 4)) % 4);
    const base64Safe = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
    const brut = atob(base64Safe);
    const tableau = new Uint8Array(brut.length);
    for (let i = 0; i < brut.length; i++) tableau[i] = brut.charCodeAt(i);
    return tableau;
}

self.addEventListener("pushsubscriptionchange", (event) => {
    if (!VAPID_PUBLIC_KEY) return;
    event.waitUntil(
        self.registration.pushManager
            .subscribe({userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)})
            .then((abonnement) =>
                fetch(URL_ABONNEMENT_PUSH, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {"Content-Type": "application/json", "X-CSRFToken": CSRF_TOKEN},
                    body: JSON.stringify(abonnement),
                })
            )
            .catch(() => { /* pas de session active : reessai a la prochaine ouverture de page */ })
    );
});

// Notification push (voir notifications/push.py) : s'affiche même app/onglet
// fermé, tant que l'appareil est en ligne au moment de la reception. Si
// l'appareil est hors ligne, le service de push (FCM sur Android/Chrome) la
// retient et la livre dès la reconnexion — comportement natif, rien à coder ici.
self.addEventListener("push", (event) => {
    let donnees = {titre: "FRPS Nord en Ligne", corps: "Nouvelle notification", url: "/"};
    if (event.data) {
        try { donnees = event.data.json(); } catch (e) { donnees.corps = event.data.text(); }
    }
    event.waitUntil(
        self.registration.showNotification(donnees.titre, {
            body: donnees.corps,
            icon: "{% static 'img/icon-192.png' %}",
            badge: "{% static 'img/icon-192.png' %}",
            data: {url: donnees.url || "/"},
        })
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = event.notification.data && event.notification.data.url ? event.notification.data.url : "/";
    event.waitUntil(
        (async () => {
            const clients = await self.clients.matchAll({type: "window", includeUncontrolled: true});
            for (const client of clients) {
                if (client.url.includes(self.location.origin) && "focus" in client) {
                    client.navigate(url);
                    return client.focus();
                }
            }
            return self.clients.openWindow(url);
        })()
    );
});

self.addEventListener("fetch", (event) => {
    const requete = event.request;
    if (requete.method !== "GET") return;

    const url = new URL(requete.url);
    if (url.origin !== self.location.origin) return;
    if (HORS_PERIMETRE.some((motif) => motif.test(url.pathname))) return;
    // Exports Excel des statistiques : ce sont des téléchargements, pas des pages.
    if (url.searchParams.has("export")) return;

    // Fichiers statiques : leur nom contient un hachage du contenu, ils sont donc
    // immuables et peuvent être servis depuis le cache sans risque de péremption.
    if (url.pathname.startsWith(PREFIXE_STATIC)) {
        event.respondWith(cacheDabord(requete));
        return;
    }

    // Pages : réseau d'abord (stock et jeton CSRF doivent être à jour), repli sur
    // la dernière version consultée, puis sur la page « hors ligne ».
    if (requete.mode === "navigate") {
        event.respondWith(reseauDabord(event));
    }
});

async function cacheDabord(requete) {
    const cache = await caches.open(CACHE_COQUILLE);
    const enCache = await cache.match(requete);
    if (enCache) return enCache;

    const reponse = await fetch(requete);
    if (reponse.ok) cache.put(requete, reponse.clone());
    return reponse;
}

async function reseauDabord(event) {
    const requete = event.request;
    const cache = await caches.open(CACHE_PAGES);
    const reseau = fetch(requete);
    const enCache = await cache.match(requete);

    if (enCache) {
        // Une version consultable existe déjà : inutile de faire patienter la FOSA
        // plus de quelques secondes, on l'affiche et la page se rafraîchira à la
        // prochaine ouverture, une fois la requête arrivée à son terme.
        try {
            const reponse = await avecDelaiMaximum(reseau, DELAI_RESEAU_MS);
            mettreEnCache(cache, requete, reponse);
            return reponse;
        } catch (erreur) {
            event.waitUntil(
                reseau.then((reponse) => mettreEnCache(cache, requete, reponse)).catch(() => {})
            );
            return enCache;
        }
    }

    // Rien en cache : abandonner au bout de quelques secondes ne servirait à rien
    // (il n'y a pas de solution de repli à afficher), on laisse donc le réseau aller
    // à son terme, si lent soit-il.
    try {
        const reponse = await reseau;
        mettreEnCache(cache, requete, reponse);
        return reponse;
    } catch (erreur) {
        return (await caches.match(PAGE_HORS_LIGNE)) || Response.error();
    }
}

// On ne met en cache que du HTML : jamais un PDF ni un export Excel.
function mettreEnCache(cache, requete, reponse) {
    const type = reponse.headers.get("Content-Type") || "";
    if (reponse.ok && type.includes("text/html")) {
        cache.put(requete, reponse.clone());
    }
}

function avecDelaiMaximum(promesse, delai) {
    return new Promise((resoudre, rejeter) => {
        const minuteur = setTimeout(() => rejeter(new Error("delai depasse")), delai);
        promesse.then(
            (valeur) => {
                clearTimeout(minuteur);
                resoudre(valeur);
            },
            (erreur) => {
                clearTimeout(minuteur);
                rejeter(erreur);
            }
        );
    });
}
