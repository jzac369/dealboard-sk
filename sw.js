// ── Service worker HenKukaj.sk ────────────────────────────────────────
// Robí z webu inštalovateľnú aplikáciu a drží ju použiteľnú aj pri
// slabom signáli:
//  - stránky (navigácia): najprv sieť, pri výpadku posledná uložená
//    verzia, inak offline stránka. Obsah je tak vždy čerstvý.
//  - obrázky, logá, ikony z vlastnej domény: hneď z pamäte a na pozadí
//    sa obnovia (stale-while-revalidate).
//  - dáta (JSON s cenami leteniek a pod.): najprv sieť.
//  - cudzie domény (Firebase, Google, reklamy) a admin sa vôbec
//    nezachytávajú - idú priamo, ako bez service workera.
// Pri zmene tohto súboru zvýš VERZIA, staré pamäte sa zmažú.
const VERZIA = 'hk-v1';
const STALE = ['/', '/offline.html', '/manifest.json', '/images/logo.png',
  '/assets/icon-192.png?v=2', '/assets/icon-512.png?v=2', '/assets/images/deal-bez-fotky.webp'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERZIA).then(c => c.addAll(STALE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(k => Promise.all(k.filter(x => x !== VERZIA).map(x => caches.delete(x))))
    .then(() => self.clients.claim()));
});

async function siet(req, zaloha) {
  const c = await caches.open(VERZIA);
  try {
    const r = await fetch(req);
    if (r.ok) c.put(req, r.clone());
    return r;
  } catch (e) {
    return (await c.match(req, { ignoreSearch: req.mode === 'navigate' })) || (zaloha && await c.match(zaloha)) || Response.error();
  }
}

async function pamat(req) {
  const c = await caches.open(VERZIA);
  const ulozena = await c.match(req);
  const nova = fetch(req).then(r => { if (r.ok) c.put(req, r.clone()); return r; }).catch(() => null);
  return ulozena || (await nova) || Response.error();
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/admin') || url.pathname.startsWith('/assets/admin/')) return;
  if (req.mode === 'navigate') { e.respondWith(siet(req, '/offline.html')); return; }
  if (/\.(json|xml|txt)$/.test(url.pathname)) { e.respondWith(siet(req)); return; }
  if (/\.(png|jpe?g|webp|gif|svg|ico|css|js|woff2?)$/.test(url.pathname)) { e.respondWith(pamat(req)); return; }
});
