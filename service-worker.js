/* Hot 100 学习站离线缓存（网络优先，离线回退缓存；API 一律走网络） */
const VERSION = "hot100-v2";
const STATIC_PREFIX = ["/index.html", "/assets/", "/library/assets/", "/library/", "/00-总览/", "/01-基础/", "/02-专题/", "/03-题解/", "/04-模板/", "/05-可视化/", "/maintenance.html", "/guide.html", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(["./index.html"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/data/") || url.pathname.startsWith("/tools/")) return;
  const isStatic = STATIC_PREFIX.some((prefix) => url.pathname.startsWith(prefix)) || url.pathname === "/" || url.pathname.endsWith("/index.html");
  if (!isStatic) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(VERSION).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request, { ignoreSearch: true }).then((cached) => cached || caches.match("./index.html"))
      )
  );
});
