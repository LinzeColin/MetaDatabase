const CACHE = "social-archive-ui-v006-r1";
const ASSETS = [
  "/",
  "/assets/styles.css?v=006-r1",
  "/assets/app.js?v=006-r1",
  "/assets/favicon.svg",
  "/assets/manifest.webmanifest?v=006-r1"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(ASSETS))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || new URL(event.request.url).origin !== location.origin) return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone())).catch(() => {});
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
