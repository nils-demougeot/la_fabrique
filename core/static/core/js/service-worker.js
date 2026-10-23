/*
 * Service worker de La Fabrique.
 * Objectif : permettre l'installation de la PWA. On ne fait volontairement
 * pas de cache agressif de tout le site (l'app est très dynamique côté
 * serveur via htmx) — seuls quelques assets statiques immuables sont mis en
 * cache, en stratégie stale-while-revalidate, pour accélérer les visites
 * répétées et donner un minimum de tolérance hors-ligne. Les navigations
 * qui échouent faute de réseau reçoivent une page « hors ligne » intégrée.
 */

const CACHE_NAME = 'la-fabrique-v2';
const PRECACHE_URLS = [
  '/static/core/images/favicon/favicon-logo.png',
  '/static/core/images/logo-la-fabrique.svg',
  '/static/core/images/icons/pwa/icon-192.png',
];

// Page affichée quand l'appli installée est ouverte sans réseau : sans elle,
// le navigateur montre son propre écran d'erreur (le dinosaure), ce qui casse
// l'illusion d'une vraie application. Autonome (aucune ressource externe).
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#1FA85C">
<title>La Fabrique — hors ligne</title>
<style>
  body { margin: 0; min-height: 100dvh; display: flex; align-items: center; justify-content: center;
         background: #FFFDF8; color: #14120F; font-family: system-ui, -apple-system, sans-serif; text-align: center; }
  main { padding: 32px 24px; max-width: 340px; }
  img { width: 84px; height: 84px; border-radius: 22px; }
  h1 { font-size: 22px; margin: 22px 0 8px; letter-spacing: -0.02em; }
  p { color: #8E877E; font-size: 15px; line-height: 1.5; margin: 0 0 24px; }
  button { font: inherit; font-weight: 700; font-size: 15px; border: 0; border-radius: 999px;
           padding: 14px 26px; background: #14120F; color: #FFFDF8; cursor: pointer; }
</style></head>
<body><main>
  <img src="/static/core/images/icons/pwa/icon-192.png" alt="">
  <h1>Pas de connexion</h1>
  <p>La Fabrique a besoin d'internet pour charger vos tissus et vos patrons. Vérifiez votre réseau puis réessayez.</p>
  <button onclick="location.reload()">Réessayer</button>
</main></body></html>`;

self.addEventListener('install', (event) => {
  // Pré-cache au mieux : si le stockage est indisponible (navigation privée,
  // quota plein), le SW doit quand même s'installer, sinon l'appli perd sa
  // page hors ligne pour une simple optimisation.
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      ))
      .catch(() => {})
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

  // Navigation pleine page : toujours le réseau ; la page hors ligne n'est
  // qu'un repli quand il ne répond pas. (Les navigations htmx sont des XHR,
  // pas des « navigate » : elles ne passent pas par ici.)
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => new Response(OFFLINE_HTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      }))
    );
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
    ).catch(() => fetch(request))
  );
});
