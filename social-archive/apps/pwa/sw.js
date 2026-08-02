const CACHE = "social-archive-ui-v005-r1";
const ASSETS = ["/", "/assets/styles.css", "/assets/app.js?v=005-r1", "/assets/favicon.svg"];

self.addEventListener("install", event => {
  event.waitUntil(Promise.all([
    self.skipWaiting(),
    caches.open(CACHE).then(cache => cache.addAll(ASSETS)).catch(() => {}),
  ]));
});

self.addEventListener("activate", event => {
  event.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE).map(key => caches.delete(key)),
    )),
  ]));
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || new URL(event.request.url).origin !== location.origin) return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(event.request, copy)).catch(() => {});
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});
