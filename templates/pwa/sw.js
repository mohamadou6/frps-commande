{% load static %}// Service worker de l'application FRPS Nord en Ligne.
// Rendu par Django (voir frps_project/pwa.py) : les URL ci-dessous sont donc les
// URL hachées réelles, et ce fichier change dès qu'un fichier statique change —
// ce qui suffit au navigateur pour détecter une mise à jour.

const VERSION = "v1";
const CACHE_COQUILLE = "frps-coquille-" + VERSION; // ressources fixes de l'app
const CACHE_PAGES = "frps-pages-" + VERSION; // pages HTML déjà consultées
const PAGE_HORS_LIGNE = "{% url 'hors_ligne' %}";
const PREFIXE_STATIC = "{% get_static_prefix %}";

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

// Jamais interceptées : l'admin Django, et les pages d'authentification dont le
// jeton CSRF doit toujours être frais (un 403 au premier login sur mobile a déjà
// été corrigé une fois par un `never_cache`, ne pas le réintroduire par le cache).
const HORS_PERIMETRE = [/^\/admin\//, /^\/login\/?$/, /^\/logout\/?$/];

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

self.addEventListener("fetch", (event) => {
    const requete = event.request;
    if (requete.method !== "GET") return;

    const url = new URL(requete.url);
    if (url.origin !== self.location.origin) return;
    if (HORS_PERIMETRE.some((motif) => motif.test(url.pathname))) return;

    // Fichiers statiques : leur nom contient un hachage du contenu, ils sont donc
    // immuables et peuvent être servis depuis le cache sans risque de péremption.
    if (url.pathname.startsWith(PREFIXE_STATIC)) {
        event.respondWith(cacheDabord(requete));
        return;
    }

    // Pages : réseau d'abord (stock et jeton CSRF doivent être à jour), repli sur
    // la dernière version consultée, puis sur la page « hors ligne ».
    if (requete.mode === "navigate") {
        event.respondWith(reseauDabord(requete));
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

async function reseauDabord(requete) {
    const cache = await caches.open(CACHE_PAGES);
    try {
        const reponse = await avecDelaiMaximum(requete);
        const type = reponse.headers.get("Content-Type") || "";
        // On ne met en cache que du HTML : surtout pas les PDF de bon de commande.
        if (reponse.ok && type.includes("text/html")) {
            cache.put(requete, reponse.clone());
        }
        return reponse;
    } catch (erreur) {
        const enCache = await cache.match(requete);
        if (enCache) return enCache;
        return (await caches.match(PAGE_HORS_LIGNE)) || Response.error();
    }
}

function avecDelaiMaximum(requete) {
    return new Promise((resoudre, rejeter) => {
        const minuteur = setTimeout(() => rejeter(new Error("delai depasse")), DELAI_RESEAU_MS);
        fetch(requete).then(
            (reponse) => {
                clearTimeout(minuteur);
                resoudre(reponse);
            },
            (erreur) => {
                clearTimeout(minuteur);
                rejeter(erreur);
            }
        );
    });
}
