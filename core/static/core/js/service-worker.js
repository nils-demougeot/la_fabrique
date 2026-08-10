/*
 * Service worker de La Fabrique.
 * Objectif : permettre l'installation de la PWA. On ne fait volontairement
 * pas de cache agressif de tout le site (l'app est très dynamique côté
 * serveur via htmx) — seuls quelques assets statiques immuables sont mis en
 * cache, en stratégie stale-while-revalidate, pour accélérer les visites
 * répétées et donner un minimum de tolérance hors-ligne.
 */

const CACHE_NAME = 'la-fabrique-v1';
const PRECACHE_URLS = [
  '/static/core/images/favicon/favicon-logo.png',
  '/static/core/images/logo-la-fabrique.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Seules les requêtes GET même origine sont interceptées : on laisse tout
  // le reste (navigation HTML, API, htmx, cross-origin) passer directement
  // au réseau pour ne jamais servir de contenu périmé.
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  const isStaticAsset = request.url.includes('/static/');
  if (!isStaticAsset) {
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then((cache) =>
      cache.match(request).then((cached) => {
        const network = fetch(request).then((response) => {
          if (response.ok) cache.put(request, response.clone());
          return response;
        }).catch(() => cached);
        return cached || network;
      })
    )
  );
});
