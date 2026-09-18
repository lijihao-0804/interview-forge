/* Hot 100 学习站缓存兜底（在线优先；动态 API 一律走网络） */
// Bump with every deploy that changes shell/runtime assets. Navigation is
// network-first below, so clients can self-upgrade without manual cache clear.
const VERSION = "hot100-v9-20260919";
const STATIC_PREFIX = ["/cockpit.html", "/index.html", "/pages/", "/assets/", "/library/assets/", "/library/", "/00-总览/", "/01-基础/", "/02-专题/", "/03-题解/", "/04-模板/", "/05-可视化/", "/maintenance.html", "/guide.html", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  const precache = ["./cockpit.html", "./index.html", "./pages/history.html"];
  event.waitUntil(
    caches.open(VERSION).then((cache) =>
      Promise.all(precache.map((url) => cache.add(url).catch(() => undefined)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key)))),
      self.clients.claim(),
    ])
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/data/") || url.pathname.startsWith("/tools/")) return;
  const isNavigation = event.request.mode === "navigate";
  const isStatic = isNavigation || STATIC_PREFIX.some((prefix) => url.pathname.startsWith(prefix)) || url.pathname === "/" || url.pathname.endsWith("/index.html");
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
      .catch(() => caches.match(event.request, { ignoreSearch: true }).then((cached) => {
        if (cached) return cached;
        // 只有页面导航允许回退到首页；CSS/JS/图片失败时不能返回 HTML。
        if (event.request.mode === "navigate") return caches.match("./index.html");
        return Response.error();
      }))
  );
});
