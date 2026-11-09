// Offline cache: pages, data and photos are kept after the first visit, so the player works
// at a field with one bar of signal. Bump VERSION when files change so phones refresh.
const VERSION = 'yae-v34';
const CORE = ['./', './index.html', './play.html', './week.html', './print.html', './start.html', './gear.html', './recovery.html', './lessons.html', './install.html', './data/lessons.json', './data/yae.json', './manifest.json'];
self.addEventListener('install', e => { e.waitUntil(caches.open(VERSION).then(c => Promise.all(CORE.map(u => fetch(u, { cache: 'no-cache' }).then(r => c.put(u, r))))).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin) return;             // YouTube and fonts go straight through
  if (u.pathname.endsWith('.json') || u.pathname.endsWith('.html') || u.pathname.endsWith('/')) {
    // network first, cache as fallback: data and pages stay fresh when online
    // cache:'no-cache' makes the phone ask the server whether the page changed instead of trusting its own copy for ten minutes
    e.respondWith(fetch(e.request.url, { cache: 'no-cache', credentials: 'same-origin' }).then(r => { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
  } else {
    // photos and PDFs: cache first, they rarely change
    e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); return r; })));
  }
});
