// 缓存名必须随界面改动一起变，否则**回访用户拿到的还是旧 app.js**。
// v0.0.0.7 改了失败文案渲染（T14）与账号连接流程（T03/T06），
// 名字还停在 v006 的话，这些改动对老用户等于没发布。
// 实测踩到过：本地验 T14 时页面一直显示旧文案，就是它。
const CACHE = "social-archive-ui-v007-r1";
const ASSETS = [
  "/",
  "/assets/styles.css?v=007-r1",
  "/assets/app.js?v=007-r1",
  "/assets/favicon.svg",
  "/assets/manifest.webmanifest?v=007-r1"
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
