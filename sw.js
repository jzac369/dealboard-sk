// DealBoard.sk – Service Worker
// Cieľ: umožniť "Pridať na plochu" (installability) a základné offline cachovanie
// statického kostry stránky. Dáta z Firebase sa naďalej ťahajú naživo zo siete.

const CACHE_NAME = 'dealboard-shell-v1';
const SHELL_ASSETS = [
  './',
  './index.html'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first strategy: skús sieť, ak zlyhá (offline), použi cache.
// Toto zabezpečí, že dealy sú vždy aktuálne, ale appka sa aspoň otvorí offline.
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
