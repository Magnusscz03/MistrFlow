// MistrFlow: cache only versioned, public, same-origin shell assets. Never cache API or user data.
const CACHE = 'mistrflow-shell-v13';
const ASSETS = ['/icon-192.png','/icon-512.png','/icon-maskable-512.png','/icon.svg','/manifest.webmanifest','/brand/mark.png','/brand/favicon.png','/brand/apple-touch-icon.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(Promise.all([caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('mistrflow-') && key !== CACHE).map(key => caches.delete(key)))), self.clients.claim()])); });
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || request.mode === 'navigate') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !ASSETS.includes(url.pathname)) return;
  event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
});
