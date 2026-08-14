// 缓存名必须随界面改动一起变，否则**回访用户拿到的还是旧 app.js**。
// 实测踩到过两次：v0.0.0.7 本地验 T14 时页面一直显示旧文案，就是它；
// 2026-08-11 发现这里和 index.html 的戳从建站起就是写死的 `007-r2`，
// Cloudflare 于是拿旧的 app.js 回了 4 小时（实测 age 3794、差 2776 字节）。
// **现在它跟着产品版本走**，由 scripts/bump_version.py 每次升版自动推动。
const CACHE = "social-archive-ui-581871ce";
const ASSETS = [
  "/",
  "/assets/styles.css?v=581871ce",
  "/assets/app.js?v=581871ce",
  "/assets/favicon.svg?v=581871ce",
  "/assets/manifest.webmanifest?v=581871ce"
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
